"""Grid-search the repetition counter's joint-angle thresholds against ground-truth counts.

The counter is a finite-state machine over a smoothed joint angle. Its thresholds were set by
hand from textbook ranges; this script finds better ones from data.

Honest methodology: thresholds are selected on TRAINING workouts only and then reported on the
held-out, unseen-subject workouts. Searching on everything and quoting the best number would be
fitting the test set — the same mistake as tuning a model on its own benchmark.

Usage:
    python ml/scripts/tune_rep_counter.py --landmarks ml/data/landmarks/mmfit.csv \
        --labels ml/data/mmfit_rep_counts.csv --test-participants w00 w05 w12 w13 w20
    # add --apply to write the winning thresholds into backend/app/services/rep_counter.py
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from dataclasses import replace
from glob import glob
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fitai_ml.data import BACKEND_DIR, ML_DIR, load_landmark_tables, ps  # noqa: E402

from app.services.rep_counter import REP_CONFIGS, RepConfig, RepCounter, combined_angle  # noqa: E402

# Search ranges per exercise, centred on the current hand-set values.
# start = the "rest" end of the movement, target = the end that must be reached for a rep.
GRIDS: dict[str, dict[str, list]] = {
    "squat": {"start": [140, 145, 150, 155, 160, 165], "target": [90, 100, 110, 120, 130, 140]},
    "lunge": {"start": [140, 145, 150, 155, 160, 165], "target": [95, 105, 115, 125, 135, 145]},
    "push_up": {"start": [135, 140, 145, 150, 155, 160], "target": [85, 95, 105, 115, 125, 135]},
    "biceps_curl": {"start": [130, 140, 145, 150, 155, 160], "target": [55, 65, 75, 85, 95, 105]},
    "shoulder_press": {"start": [85, 95, 105, 115, 125], "target": [135, 145, 150, 155, 160, 165]},
}
SMOOTHING = [3, 5, 9]
HYSTERESIS = [5.0, 8.0, 12.0]


def angle_series(sample: pd.DataFrame, config: RepConfig, min_visibility: float) -> list[float | None]:
    """Pre-compute the joint angle per frame once, so the grid search only re-runs the state machine."""
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


def count_reps(angles: list[float | None], config: RepConfig, min_visibility: float) -> int:
    counter = RepCounter(config, min_visibility)
    for a in angles:
        counter.update_angle(a)
    return counter.count


def score(samples: list[tuple[list[float | None], int]], config: RepConfig, min_visibility: float) -> dict:
    errors = [abs(count_reps(angles, config, min_visibility) - truth) for angles, truth in samples]
    zeros = sum(1 for angles, _ in samples if count_reps(angles, config, min_visibility) == 0)
    return {
        "n": len(errors),
        "mae": round(statistics.mean(errors), 3) if errors else None,
        "within_one_pct": round(100 * sum(1 for e in errors if e <= 1) / len(errors), 1) if errors else None,
        "zero_count_sets": zeros,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--landmarks", nargs="+", required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--test-participants", nargs="+", required=True, help="held out of tuning entirely")
    parser.add_argument("--min-visibility", type=float, default=0.5)
    parser.add_argument("--out", type=Path, default=ML_DIR / "results" / "rep_counter_tuning.json")
    parser.add_argument("--apply", action="store_true", help="write the winning thresholds into rep_counter.py")
    args = parser.parse_args()

    paths = [Path(p) for pattern in args.landmarks for p in (glob(pattern) or [pattern])]
    df = load_landmark_tables(paths)
    truth = pd.read_csv(args.labels, dtype={"sample_id": str}).set_index("sample_id")["true_repetitions"]
    test_people = set(args.test_participants)

    print("pre-computing joint angles per sample...", flush=True)
    data: dict[str, dict[str, list]] = {ex: {"tune": [], "test": []} for ex in REP_CONFIGS}
    for sample_id, sample in df.groupby("sample_id", sort=False):
        if sample_id not in truth.index:
            continue
        exercise = sample.iloc[0]["exercise_label"]
        if exercise not in REP_CONFIGS:
            continue
        angles = angle_series(sample, REP_CONFIGS[exercise], args.min_visibility)
        split = "test" if sample.iloc[0]["participant_id"] in test_people else "tune"
        data[exercise][split].append((angles, int(truth[sample_id])))

    results = {}
    for exercise, cfg in REP_CONFIGS.items():
        tune, test = data[exercise]["tune"], data[exercise]["test"]
        if not tune or not test:
            print(f"{exercise}: not enough data (tune={len(tune)}, test={len(test)}) — skipped")
            continue
        grid = GRIDS[exercise]
        candidates = [
            replace(cfg, start_threshold=float(s), target_threshold=float(t), smoothing_window=sm, hysteresis=hy)
            for s in grid["start"] for t in grid["target"] for sm in SMOOTHING for hy in HYSTERESIS
            # the target must stay on the far side of the start for the phase logic to mean anything
            if (t < s - 20 if cfg.start_is_high else t > s + 20)
        ]
        print(f"{exercise}: {len(candidates)} candidates on {len(tune)} tuning sets", flush=True)

        scored = []
        for cand in candidates:
            s = score(tune, cand, args.min_visibility)
            # Rank by error first, then by how rarely the counter fails to register anything at all.
            scored.append((s["mae"], s["zero_count_sets"], cand, s))
        scored.sort(key=lambda r: (r[0], r[1]))
        best_mae, _, best, best_tune = scored[0]

        results[exercise] = {
            "current": {"start": cfg.start_threshold, "target": cfg.target_threshold,
                        "smoothing_window": cfg.smoothing_window, "hysteresis": cfg.hysteresis},
            "tuned": {"start": best.start_threshold, "target": best.target_threshold,
                      "smoothing_window": best.smoothing_window, "hysteresis": best.hysteresis},
            "tune_split": {"current": score(tune, cfg, args.min_visibility), "tuned": best_tune},
            "test_split": {"current": score(test, cfg, args.min_visibility), "tuned": score(test, best, args.min_visibility)},
        }  # fmt: skip
        r = results[exercise]
        print(f"  current  start {cfg.start_threshold:>5} target {cfg.target_threshold:>5} -> test MAE {r['test_split']['current']['mae']}")
        print(f"  tuned    start {best.start_threshold:>5} target {best.target_threshold:>5} -> test MAE {r['test_split']['tuned']['mae']}  (tuning MAE {best_mae})")

    if not results:
        raise SystemExit("nothing tuned")

    overall = {
        split: {
            which: round(
                sum(results[e][f"{split}_split"][which]["mae"] * results[e][f"{split}_split"][which]["n"] for e in results)
                / sum(results[e][f"{split}_split"][which]["n"] for e in results), 3)
            for which in ("current", "tuned")
        }
        for split in ("tune", "test")
    }  # fmt: skip
    results["_overall_mae"] = overall
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(results, indent=2), encoding="utf-8")

    print("\n" + "=" * 70)
    print(f"overall MAE on HELD-OUT workouts: {overall['test']['current']} -> {overall['test']['tuned']}")
    print(f"(tuning workouts: {overall['tune']['current']} -> {overall['tune']['tuned']})")
    print(f"written to {args.out}")

    if args.apply:
        path = BACKEND_DIR / "app" / "services" / "rep_counter.py"
        src = path.read_text(encoding="utf-8")
        for exercise, r in results.items():
            if exercise.startswith("_"):
                continue
            t = r["tuned"]
            pattern = rf'("{exercise}": RepConfig\("{exercise}", \([^)]*\), "[a-z_]+", (?:True|False), )[\d.]+, [\d.]+(, [\d.]+, \d+)?\)'
            new = rf'\g<1>{t["start"]}, {t["target"]}, {t["hysteresis"]}, {t["smoothing_window"]})'
            src, n = re.subn(pattern, new, src)
            if n != 1:
                raise SystemExit(f"could not rewrite config for {exercise} (matched {n} times)")
        path.write_text(src, encoding="utf-8")
        print(f"applied tuned thresholds to {path}")


if __name__ == "__main__":
    main()
