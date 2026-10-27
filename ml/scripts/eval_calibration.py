"""Compare repetition-counting strategies against MM-Fit's ground-truth counts.

    hand-set     the original thresholds, chosen from textbook joint ranges
    tuned-fixed  the best fixed thresholds found by tune_rep_counter.py (fitted to these workouts)
    calibrated   per-session calibration: thresholds derived from the person's own range of motion

Only `tuned-fixed` saw any of this data during fitting, and it was fitted on the training
workouts alone. `calibrated` fits nothing — it adapts within each set — so the comparison on the
held-out workouts is the fair one.

Usage:
    python ml/scripts/eval_calibration.py --landmarks ml/data/landmarks/mmfit.csv \
        --labels ml/data/mmfit_rep_counts.csv --test-participants w00 w05 w12 w13 w20
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from dataclasses import replace
from glob import glob
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fitai_ml.data import ML_DIR, load_landmark_tables, ps  # noqa: E402

from app.services.rep_counter import REP_CONFIGS, CalibrationSettings, RepCounter, combined_angle  # noqa: E402

NO_CAL = CalibrationSettings(enabled=False)


def angle_series(sample: pd.DataFrame, config, min_visibility: float) -> list[float | None]:
    x = sample[[f"landmark_{i}_x" for i in range(ps.NUM_LANDMARKS)]].to_numpy(np.float32)
    y = sample[[f"landmark_{i}_y" for i in range(ps.NUM_LANDMARKS)]].to_numpy(np.float32)
    v = sample[[f"landmark_{i}_visibility" for i in range(ps.NUM_LANDMARKS)]].to_numpy(np.float32)
    w = sample["image_width"].to_numpy(np.float64)
    h = sample["image_height"].to_numpy(np.float64)
    out: list[float | None] = []
    for t in range(len(sample)):
        arr = np.stack([x[t], y[t], np.zeros_like(x[t]), v[t]], axis=1)
        if np.isfinite(w[t]) and np.isfinite(h[t]) and h[t] > 0:
            arr = ps.aspect_corrected(arr, w[t], h[t])
        out.append(combined_angle(arr, config, min_visibility))
    return out


def count(angles, config, calibration, min_visibility: float) -> int:
    counter = RepCounter(config, min_visibility, calibration=calibration)
    for a in angles:
        counter.update_angle(a)
    return counter.count


def stats(errors: list[int], zeros: int) -> dict:
    return {
        "n": len(errors),
        "mae": round(statistics.mean(errors), 3),
        "within_one_pct": round(100 * sum(1 for e in errors if e <= 1) / len(errors), 1),
        "zero_count_sets": zeros,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--landmarks", nargs="+", required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--test-participants", nargs="+", required=True)
    parser.add_argument("--tuning", type=Path, default=ML_DIR / "results" / "rep_counter_tuning.json")
    parser.add_argument("--min-visibility", type=float, default=0.5)
    parser.add_argument("--out", type=Path, default=ML_DIR / "results" / "rep_counter_calibration.json")
    args = parser.parse_args()

    tuned = json.loads(args.tuning.read_text(encoding="utf-8")) if args.tuning.exists() else {}
    df = load_landmark_tables([Path(p) for pattern in args.landmarks for p in (glob(pattern) or [pattern])])
    truth = pd.read_csv(args.labels, dtype={"sample_id": str}).set_index("sample_id")["true_repetitions"]
    test_people = set(args.test_participants)

    results: dict[str, dict] = {}
    pooled: dict[str, list[int]] = {"hand-set": [], "tuned-fixed": [], "calibrated": []}
    pooled_zeros = dict.fromkeys(pooled, 0)

    for exercise, base in REP_CONFIGS.items():
        strategies = {"hand-set": (base, NO_CAL), "calibrated": (base, CalibrationSettings())}
        if exercise in tuned:
            t = tuned[exercise]["tuned"]
            strategies["tuned-fixed"] = (
                replace(base, start_threshold=t["start"], target_threshold=t["target"],
                        hysteresis=t["hysteresis"], smoothing_window=t["smoothing_window"]),
                NO_CAL,
            )  # fmt: skip

        errors: dict[str, list[int]] = {k: [] for k in strategies}
        zeros = dict.fromkeys(strategies, 0)
        for sample_id, sample in df.groupby("sample_id", sort=False):
            if sample_id not in truth.index or sample.iloc[0]["exercise_label"] != exercise:
                continue
            if sample.iloc[0]["participant_id"] not in test_people:
                continue  # held-out workouts only
            angles = angle_series(sample, base, args.min_visibility)
            for name, (cfg, cal) in strategies.items():
                got = count(angles, cfg, cal, args.min_visibility)
                errors[name].append(abs(got - int(truth[sample_id])))
                zeros[name] += got == 0
        if not next(iter(errors.values())):
            continue
        results[exercise] = {name: stats(errors[name], zeros[name]) for name in strategies}
        for name in strategies:
            pooled[name].extend(errors[name])
            pooled_zeros[name] += zeros[name]
        line = "  ".join(f"{name} MAE {results[exercise][name]['mae']:<6}" for name in strategies)
        print(f"{exercise:<16} {line}")

    overall = {name: stats(errs, pooled_zeros[name]) for name, errs in pooled.items() if errs}
    results["_overall"] = overall
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(results, indent=2), encoding="utf-8")

    print("\n" + "=" * 72)
    print(f"{'strategy':<14}{'MAE':>8}{'within +/-1':>14}{'zero-count sets':>18}")
    for name, s in overall.items():
        print(f"{name:<14}{s['mae']:>8}{s['within_one_pct']:>13}%{s['zero_count_sets']:>18}")
    print(f"\nheld-out workouts: {', '.join(sorted(test_people))} ({overall['hand-set']['n']} sets)")
    print(f"written to {args.out}")


if __name__ == "__main__":
    main()
