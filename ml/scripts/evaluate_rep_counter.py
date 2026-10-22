"""Evaluate the angle-based repetition counter against manually counted repetitions.

Usage:
  python ml/scripts/evaluate_rep_counter.py --landmarks ml/data/landmarks/*.csv --labels ml/data/rep_counts.csv

rep_counts.csv columns: sample_id, true_repetitions
Reports mean absolute counting error (MAE) and the percentage of samples within one count.
"""

from __future__ import annotations

import argparse
import json
import sys
from glob import glob
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fitai_ml.data import ML_DIR, load_landmark_tables, ps, row_to_array  # noqa: E402

from app.services.rep_counter import make_rep_counter  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--landmarks", nargs="+", required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--min-visibility", type=float, default=0.5)
    parser.add_argument("--out", type=Path, default=ML_DIR / "results" / "rep_counter_metrics.json")
    args = parser.parse_args()

    df = load_landmark_tables([Path(p) for pattern in args.landmarks for p in (glob(pattern) or [pattern])])
    labels = pd.read_csv(args.labels, dtype={"sample_id": str}).set_index("sample_id")["true_repetitions"]

    rows, per_exercise = [], {}
    for sample_id, sample in df.groupby("sample_id", sort=False):
        if sample_id not in labels.index:
            continue
        exercise = sample.iloc[0]["exercise_label"]
        counter = make_rep_counter(exercise, args.min_visibility)
        for _, row in sample.iterrows():
            arr = row_to_array(row)
            if np.isfinite(row["image_width"]) and np.isfinite(row["image_height"]):
                arr = ps.aspect_corrected(arr, row["image_width"], row["image_height"])
            counter.update(arr)
        error = abs(counter.count - int(labels[sample_id]))
        rows.append({"sample_id": sample_id, "exercise": exercise, "predicted": counter.count, "true": int(labels[sample_id]), "abs_error": error})
        per_exercise.setdefault(exercise, []).append(error)

    if not rows:
        raise SystemExit("no labelled samples matched the landmark files")

    def stats(errors):
        e = np.asarray(errors)
        return {"n": int(len(e)), "mae": round(float(e.mean()), 3), "within_one_pct": round(float((e <= 1).mean() * 100), 1)}

    result = {"overall": stats([r["abs_error"] for r in rows]), "per_exercise": {k: stats(v) for k, v in per_exercise.items()}, "samples": rows}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("overall", "per_exercise")}, indent=2))


if __name__ == "__main__":
    main()
