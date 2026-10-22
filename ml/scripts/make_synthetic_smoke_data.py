"""Generate SYNTHETIC landmark recordings to smoke-test the pipeline end to end.

!! The output is procedurally generated stick-figure motion, NOT human data. !!
Use it only to check that build_sequences / train / evaluate run. Never report
metrics obtained on it as model performance.

Usage:
  python ml/scripts/make_synthetic_smoke_data.py --out ml/data/synthetic_smoke.csv --participants 6
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fitai_ml.data import ALL_COLUMNS, ps  # noqa: E402

EXERCISES = ["squat", "lunge", "push_up", "biceps_curl", "shoulder_press"]


def base_pose() -> np.ndarray:
    arr = np.zeros((ps.NUM_LANDMARKS, 3), dtype=np.float32)
    arr[:, 2] = 0.95
    arr[:, :2] = (0.5, 0.2)  # head points
    for side, dx in (("left", 0.08), ("right", -0.08)):
        coords = {"shoulder": (0.5 + dx, 0.32), "elbow": (0.5 + dx * 1.2, 0.45), "wrist": (0.5 + dx * 1.2, 0.57),
                  "hip": (0.5 + dx * 0.7, 0.58), "knee": (0.5 + dx * 0.7, 0.74), "ankle": (0.5 + dx * 0.7, 0.9)}  # fmt: skip
        for joint, (x, y) in coords.items():
            arr[ps.IDX[f"{side}_{joint}"], :2] = (x, y)
        for extra, src in (("pinky", "wrist"), ("index", "wrist"), ("thumb", "wrist"), ("heel", "ankle"), ("foot_index", "ankle")):
            arr[ps.IDX[f"{side}_{extra}"], :2] = arr[ps.IDX[f"{side}_{src}"], :2]
    return arr


def pose_at(exercise: str, phase: float, error: bool) -> np.ndarray:
    """phase in [0, 1]: 0 = start, 1 = bottom of the movement."""
    a = base_pose()
    s = math.sin(phase * math.pi / 2)
    for side, dx in (("left", 0.08), ("right", -0.08)):
        i = lambda j: ps.IDX[f"{side}_{j}"]  # noqa: E731
        if exercise == "squat":
            drop = 0.16 * s
            for j in ("shoulder", "elbow", "wrist", "hip"):
                a[i(j), 1] += drop
            a[i("knee"), 0] += dx * (0.6 * s if not error else -0.9 * s)
            a[i("knee"), 1] += drop * 0.4
        elif exercise == "lunge":
            drop = 0.12 * s
            for j in ("shoulder", "elbow", "wrist", "hip"):
                a[i(j), 1] += drop
            a[i("knee"), 1] += drop * 0.5 * (1 if side == "left" else -0.2)
            if error:
                a[i("shoulder"), 0] += 0.08 * s
        elif exercise == "push_up":
            a[i("elbow"), 0] += dx * 1.5 * s
            a[i("wrist"), 1] -= 0.05 * s
            a[i("hip"), 1] += (0.06 if error else 0.0) * s
        elif exercise == "biceps_curl":
            a[i("wrist"), :2] = a[i("elbow"), :2] + (0.0, 0.12 * math.cos(s * 2.6))
            a[i("wrist"), 0] += dx * 0.5 * s
            if error:
                a[i("elbow"), 0] += dx * 0.8 * s
        elif exercise == "shoulder_press":
            a[i("elbow"), 1] = 0.33 - 0.12 * s
            a[i("wrist"), 1] = 0.22 - 0.1 * s - (0.0 if not error or side == "left" else -0.08 * s)
    return a


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--participants", type=int, default=6)
    parser.add_argument("--reps", type=int, default=6)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    rng = np.random.default_rng(args.seed)

    rows = []
    for p in range(args.participants):
        pid = f"SYN{p:02d}"
        scale, shift = rng.uniform(0.85, 1.15), rng.uniform(-0.05, 0.05, size=2)
        for exercise in EXERCISES:
            for form in ("correct", "error"):
                sample_id = f"{pid}_{exercise}_{form}"
                rep_frames = int(rng.integers(35, 50))
                t = 0
                for _ in range(args.reps):
                    for k in range(rep_frames):
                        phase = 1 - abs(2 * k / (rep_frames - 1) - 1)
                        arr = pose_at(exercise, phase, form == "error")
                        arr[:, :2] = (arr[:, :2] - 0.5) * scale + 0.5 + shift + rng.normal(0, 0.004, size=(ps.NUM_LANDMARKS, 2))
                        row = [sample_id, pid, exercise, "correct" if form == "correct" else "incorrect",
                               "" if form == "correct" else "synthetic_error", t, 0.95, 640, 480]  # fmt: skip
                        row += [round(float(v), 5) for v in arr.reshape(-1)]
                        rows.append(row)
                        t += 1

    import csv

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(ALL_COLUMNS)
        w.writerows(rows)
    print(f"wrote {len(rows)} SYNTHETIC frames to {args.out} (pipeline smoke test only)")


if __name__ == "__main__":
    main()
