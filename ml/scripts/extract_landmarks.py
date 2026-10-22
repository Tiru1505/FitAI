"""Extract MediaPipe pose landmarks from consented exercise videos into the FitAI CSV schema.

Only numerical landmarks are written; the videos themselves are not copied or stored.

Usage:
    python ml/scripts/extract_landmarks.py --manifest ml/data/videos_manifest.csv \
        --model ml/models/pose_landmarker_full.task --out ml/data/landmarks/recordings.csv

Manifest columns: video_path, sample_id, participant_id, exercise_label, form_label, error_label
Download the pose model (pose_landmarker_full.task) from the MediaPipe Pose Landmarker page:
https://ai.google.dev/edge/mediapipe/solutions/vision/pose_landmarker
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fitai_ml.data import ALL_COLUMNS, ps  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True, help="path to pose_landmarker_*.task")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--every-nth-frame", type=int, default=1, help="subsample frames (e.g. 2 for 60fps -> 30fps)")
    args = parser.parse_args()

    import cv2
    import mediapipe as mp
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.manifest.open(encoding="utf-8") as f:
        entries = list(csv.DictReader(f))

    with args.out.open("w", newline="", encoding="utf-8") as out:
        writer = csv.writer(out)
        writer.writerow(ALL_COLUMNS)
        for entry in entries:
            options = vision.PoseLandmarkerOptions(
                base_options=mp_python.BaseOptions(model_asset_path=str(args.model)),
                running_mode=vision.RunningMode.VIDEO,
                num_poses=1,
            )
            cap = cv2.VideoCapture(entry["video_path"])
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            width = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
            height = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
            written = frame_no = 0
            with vision.PoseLandmarker.create_from_options(options) as landmarker:
                while True:
                    ok, frame = cap.read()
                    if not ok:
                        break
                    frame_no += 1
                    if (frame_no - 1) % args.every_nth_frame:
                        continue
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                    result = landmarker.detect_for_video(image, int(frame_no * 1000 / fps))
                    if not result.pose_landmarks:
                        continue  # no person detected: skip frame (it would be flagged as missing anyway)
                    lms = result.pose_landmarks[0]
                    vis = [lm.visibility for lm in lms]
                    row = [
                        entry["sample_id"], entry["participant_id"], entry["exercise_label"],
                        entry.get("form_label") or "correct", entry.get("error_label") or "",
                        written, round(sum(vis) / len(vis), 4), width, height,
                    ]  # fmt: skip
                    for lm in lms[: ps.NUM_LANDMARKS]:
                        row += [round(lm.x, 5), round(lm.y, 5), round(lm.visibility, 4)]
                    writer.writerow(row)
                    written += 1
            cap.release()
            print(f"{entry['sample_id']}: {written} frames with a detected pose")


if __name__ == "__main__":
    main()
