"""Convert the MM-Fit dataset into FitAI's landmark CSV schema.

MM-Fit: Strömbäck, D., Huang, S., Radu, V. (2020). "MM-Fit: Multimodal Deep Learning for
Automatic Exercise Logging across Sensing Devices." Proc. ACM IMWUT 4(4), Article 168.
Dataset: https://mmfit.github.io/

MM-Fit ships 2D/3D pose estimates per workout plus a label file giving, for each exercise set,
(start_frame, end_frame, repetitions, activity). Five of its exercises match FitAI v1:
squats, push-ups, lunges, dumbbell shoulder press and bicep curls.

What this produces:
  * a landmark CSV in FitAI's schema (33 MediaPipe slots; MM-Fit joints are mapped into the
    matching slots, unmapped slots get visibility 0)
  * a rep-counts CSV (sample_id, true_repetitions) from MM-Fit's ground-truth counts, for
    evaluating the repetition counter

Limitation: MM-Fit has no incorrect-form labels, so every sample is labelled form_label=correct
and it cannot train the form classifier.

Usage:
    python ml/scripts/convert_mmfit.py --mmfit-dir data_sources/mmfit/mm-fit \
        --out ml/data/landmarks/mmfit.csv --rep-counts-out ml/data/mmfit_rep_counts.csv
    python ml/scripts/convert_mmfit.py --mmfit-dir data_sources/mmfit/mm-fit --inspect
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fitai_ml.data import ALL_COLUMNS, ps  # noqa: E402

ACTIVITY_MAP = {
    "squats": "squat",
    "pushups": "push_up",
    "lunges": "lunge",
    "dumbbell_shoulder_press": "shoulder_press",
    "bicep_curls": "biceps_curl",
}

# MM-Fit 2D pose uses a 17-joint COCO-style skeleton. Index -> MediaPipe landmark name.
COCO17_TO_MEDIAPIPE = {
    0: "nose",
    1: "left_eye",
    2: "right_eye",
    3: "left_ear",
    4: "right_ear",
    5: "left_shoulder",
    6: "right_shoulder",
    7: "left_elbow",
    8: "right_elbow",
    9: "left_wrist",
    10: "right_wrist",
    11: "left_hip",
    12: "right_hip",
    13: "left_knee",
    14: "right_knee",
    15: "left_ankle",
    16: "right_ankle",
}

# Some MM-Fit releases use an 18-joint OpenPose (BODY_25 subset) ordering with a neck joint.
OPENPOSE18_TO_MEDIAPIPE = {
    0: "nose",
    2: "right_shoulder",
    3: "right_elbow",
    4: "right_wrist",
    5: "left_shoulder",
    6: "left_elbow",
    7: "left_wrist",
    8: "right_hip",
    9: "right_knee",
    10: "right_ankle",
    11: "left_hip",
    12: "left_knee",
    13: "left_ankle",
    14: "right_eye",
    15: "left_eye",
    16: "right_ear",
    17: "left_ear",
}


def load_pose(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Return (frame_numbers [N], joints [N, J, 3] as x, y, confidence).

    MM-Fit stores pose as [channel, frame, 1 + joints], where column 0 is the frame number.
    The 2D pose has 2 channels (x, y) and no confidence, so confidence is set to 1 for joints
    that were detected and 0 for missing ones (which MM-Fit encodes as x = y = 0).
    """
    raw = np.load(path)
    if raw.ndim != 3 or raw.shape[0] < 2:
        raise SystemExit(f"unexpected pose array shape {raw.shape} in {path.name}")
    frames = raw[0, :, 0].astype(np.int64)
    x, y = raw[0, :, 1:], raw[1, :, 1:]
    if raw.shape[0] >= 3:
        confidence = raw[2, :, 1:]
    else:
        confidence = np.where((x == 0) & (y == 0), 0.0, 1.0)
    return frames, np.stack([x, y, confidence], axis=-1).astype(np.float32)


def choose_mapping(num_joints: int) -> dict[int, str]:
    if num_joints == 17:
        return COCO17_TO_MEDIAPIPE
    if num_joints == 18:
        return OPENPOSE18_TO_MEDIAPIPE
    raise SystemExit(f"unsupported MM-Fit skeleton with {num_joints} joints; add a mapping table")


def orientation_ok(joints: np.ndarray, mapping: dict[int, str]) -> bool:
    """Sanity check: ankles should sit below hips, which sit below shoulders (image y grows downward)."""
    inv = {name: idx for idx, name in mapping.items()}
    y = joints[:, :, 1]
    shoulder = np.nanmean(y[:, [inv["left_shoulder"], inv["right_shoulder"]]])
    hip = np.nanmean(y[:, [inv["left_hip"], inv["right_hip"]]])
    ankle = np.nanmean(y[:, [inv["left_ankle"], inv["right_ankle"]]])
    return bool(shoulder < hip < ankle)


def load_labels(path: Path) -> list[tuple[int, int, int, str]]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in csv.reader(f):
            if len(line) >= 4:
                rows.append((int(line[0]), int(line[1]), int(line[2]), line[3].strip()))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mmfit-dir", type=Path, required=True, help="extracted mm-fit/ folder containing w00, w01, ...")
    parser.add_argument("--out", type=Path, help="landmark CSV to write")
    parser.add_argument("--rep-counts-out", type=Path, help="rep-count CSV to write")
    parser.add_argument("--pose", choices=["2d", "3d"], default="2d")
    # MM-Fit 2D pose is in pixels of the 1280x720 RGB stream; the aspect ratio matters for joint angles.
    parser.add_argument("--image-width", type=float, default=1280, help="0 = infer from the coordinate range")
    parser.add_argument("--image-height", type=float, default=720)
    parser.add_argument("--min-frames", type=int, default=90, help="skip sets shorter than this many frames")
    parser.add_argument("--workouts", nargs="*", help="only convert these workout folders, e.g. w00 w01")
    parser.add_argument("--inspect", action="store_true", help="print shapes and labels, write nothing")
    args = parser.parse_args()

    workouts = sorted(d for d in args.mmfit_dir.iterdir() if d.is_dir() and d.name.startswith("w"))
    if args.workouts:
        workouts = [d for d in workouts if d.name in set(args.workouts)]
    if not workouts:
        raise SystemExit(f"no workout folders found in {args.mmfit_dir}")

    if args.inspect:
        for d in workouts[:3]:
            pose_files = sorted(d.glob("*pose*.npy"))
            print(f"\n{d.name}: {[p.name for p in d.iterdir()][:12]}")
            for p in pose_files:
                raw = np.load(p)
                print(f"  {p.name}: shape {raw.shape} dtype {raw.dtype} first row {np.round(raw[:, 0, :4], 2).tolist()}")
            label_file = next(iter(d.glob("*labels*.csv")), None)
            if label_file:
                labels = load_labels(label_file)
                print(f"  labels: {len(labels)} sets, activities {sorted({a for *_, a in labels})}")
                print(f"  first: {labels[:3]}")
        return

    if not args.out:
        raise SystemExit("--out is required unless --inspect is used")

    rows: list[list] = []
    rep_counts: list[tuple[str, int]] = []
    stats = {"workouts": 0, "sets_used": 0, "sets_skipped_activity": 0, "sets_skipped_short": 0, "frames": 0}
    per_exercise: dict[str, int] = {}

    for d in workouts:
        pose_path = next(iter(d.glob(f"*pose_{args.pose}*.npy")), None)
        label_path = next(iter(d.glob("*labels*.csv")), None)
        if pose_path is None or label_path is None:
            print(f"skipping {d.name}: missing pose or label file")
            continue
        frames, joints = load_pose(pose_path)
        mapping = choose_mapping(joints.shape[1])
        if not orientation_ok(joints, mapping):
            raise SystemExit(f"{d.name}: joint mapping failed the head-above-feet check; the skeleton layout differs")
        width = args.image_width or float(np.nanmax(joints[:, :, 0])) or 1.0
        height = args.image_height or float(np.nanmax(joints[:, :, 1])) or 1.0
        confidences = joints[:, :, 2]
        conf_max = float(np.nanmax(confidences)) if np.isfinite(confidences).any() else 1.0
        conf_scale = 1.0 if conf_max <= 1.0 else conf_max
        stats["workouts"] += 1

        for start, end, reps, activity in load_labels(label_path):
            exercise = ACTIVITY_MAP.get(activity)
            if exercise is None:
                stats["sets_skipped_activity"] += 1
                continue
            mask = (frames >= start) & (frames <= end)
            if int(mask.sum()) < args.min_frames:
                stats["sets_skipped_short"] += 1
                continue
            sample_id = f"{d.name}_{exercise}_{start}"
            set_joints = joints[mask]
            for frame_index in range(set_joints.shape[0]):
                landmarks = np.zeros((ps.NUM_LANDMARKS, 3), dtype=np.float32)  # x, y, visibility
                for joint_index, name in mapping.items():
                    x, y, conf = set_joints[frame_index, joint_index]
                    if not np.isfinite([x, y, conf]).all() or (x == 0 and y == 0):
                        continue  # missing joint: leave visibility 0
                    landmarks[ps.IDX[name]] = (
                        min(max(x / width, 0.0), 1.0),
                        min(max(y / height, 0.0), 1.0),
                        min(max(conf / conf_scale, 0.0), 1.0),
                    )
                visible = landmarks[:, 2]
                rows.append(
                    [sample_id, d.name, exercise, "correct", "", frame_index, round(float(visible[visible > 0].mean() if (visible > 0).any() else 0.0), 4), round(width), round(height)]
                    + [round(float(v), 5) for v in landmarks.reshape(-1)]
                )
            rep_counts.append((sample_id, reps))
            stats["sets_used"] += 1
            stats["frames"] += int(set_joints.shape[0])
            per_exercise[exercise] = per_exercise.get(exercise, 0) + 1

    if not rows:
        raise SystemExit("no matching exercise sets were converted")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(ALL_COLUMNS)
        writer.writerows(rows)
    if args.rep_counts_out:
        args.rep_counts_out.parent.mkdir(parents=True, exist_ok=True)
        with args.rep_counts_out.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["sample_id", "true_repetitions"])
            writer.writerows(rep_counts)

    print(f"workouts (participants): {stats['workouts']}")
    print(f"sets converted: {stats['sets_used']}  (skipped: {stats['sets_skipped_activity']} other exercises, {stats['sets_skipped_short']} too short)")
    print(f"frames written: {stats['frames']}")
    print(f"sets per exercise: {dict(sorted(per_exercise.items()))}")
    print(f"landmark CSV: {args.out}")
    if args.rep_counts_out:
        print(f"rep counts:    {args.rep_counts_out}")


if __name__ == "__main__":
    main()
