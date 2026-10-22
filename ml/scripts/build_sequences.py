"""Turn landmark recordings into fixed-length windows with a participant-independent split.

Usage:
    python ml/scripts/build_sequences.py --inputs ml/data/landmarks/*.csv --out ml/data/sequences.npz \
        --sequence-length 60 --stride 15 --val-participants P07 P08 --test-participants P09 P10

If --val/--test participants are not given, participants are shuffled with --seed and split
by --val-fraction / --test-fraction. Frames are never split randomly: every window of a
participant goes to exactly one split, so test participants never appear in training.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from glob import glob
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fitai_ml.data import load_landmark_tables, sample_features, windows  # noqa: E402


def split_participants(participants, val, test, val_fraction, test_fraction, seed):
    participants = sorted(participants)
    if val or test:
        val, test = set(val or []), set(test or [])
        unknown = (val | test) - set(participants)
        if unknown:
            raise SystemExit(f"unknown participants: {sorted(unknown)}")
        if val & test:
            raise SystemExit("a participant cannot be in both validation and test sets")
        train = [p for p in participants if p not in val | test]
        return train, sorted(val), sorted(test)
    rng = random.Random(seed)
    shuffled = participants[:]
    rng.shuffle(shuffled)
    n_test = max(1, round(len(shuffled) * test_fraction))
    n_val = max(1, round(len(shuffled) * val_fraction))
    if len(shuffled) < n_test + n_val + 1:
        raise SystemExit(f"need at least {n_test + n_val + 1} participants for a participant-independent split")
    return sorted(shuffled[n_test + n_val :]), sorted(shuffled[n_test : n_test + n_val]), sorted(shuffled[:n_test])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--inputs", nargs="+", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--sequence-length", type=int, default=60)
    parser.add_argument("--stride", type=int, default=15)
    parser.add_argument("--min-visibility", type=float, default=0.5)
    parser.add_argument("--max-low-visibility-ratio", type=float, default=0.2)
    parser.add_argument("--val-participants", nargs="*")
    parser.add_argument("--test-participants", nargs="*")
    parser.add_argument("--val-fraction", type=float, default=0.15)
    parser.add_argument("--test-fraction", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    paths = [Path(p) for pattern in args.inputs for p in (glob(pattern) or [pattern])]
    df = load_landmark_tables(paths)
    train_p, val_p, test_p = split_participants(
        df["participant_id"].unique(), args.val_participants, args.test_participants,
        args.val_fraction, args.test_fraction, args.seed,
    )  # fmt: skip
    split_of = {p: "train" for p in train_p} | {p: "val" for p in val_p} | {p: "test" for p in test_p}

    exercise_labels = sorted(df["exercise_label"].unique())
    form_labels = sorted((df["form_label"].where(df["error_label"] == "", df["error_label"])).unique())

    data = {s: {"X": [], "exercise": [], "form": [], "participant": [], "sample": []} for s in ("train", "val", "test")}
    stats = {"samples": 0, "windows_kept": 0, "windows_dropped_low_visibility": 0, "frames_low_visibility": 0}
    for sample_id, sample in df.groupby("sample_id", sort=False):
        stats["samples"] += 1
        feats, low = sample_features(sample, args.min_visibility)
        stats["frames_low_visibility"] += int(low.sum())
        first = sample.iloc[0]
        form = first["error_label"] or first["form_label"]
        split = split_of[first["participant_id"]]
        for start, end in windows(len(sample), args.sequence_length, args.stride):
            if low[start:end].mean() > args.max_low_visibility_ratio:
                stats["windows_dropped_low_visibility"] += 1
                continue
            d = data[split]
            d["X"].append(feats[start:end])
            d["exercise"].append(exercise_labels.index(first["exercise_label"]))
            d["form"].append(form_labels.index(form))
            d["participant"].append(first["participant_id"])
            d["sample"].append(sample_id)
            stats["windows_kept"] += 1

    arrays = {}
    for split, d in data.items():
        arrays[f"X_{split}"] = np.asarray(d["X"], dtype=np.float32).reshape(-1, args.sequence_length, 99)
        arrays[f"y_exercise_{split}"] = np.asarray(d["exercise"], dtype=np.int64)
        arrays[f"y_form_{split}"] = np.asarray(d["form"], dtype=np.int64)
        arrays[f"exercise_name_{split}"] = np.asarray([exercise_labels[i] for i in d["exercise"]])
        arrays[f"participant_{split}"] = np.asarray(d["participant"])
        arrays[f"sample_{split}"] = np.asarray(d["sample"])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(args.out, **arrays)

    manifest = {
        "inputs": [str(p) for p in paths],
        "sequence_length": args.sequence_length,
        "stride": args.stride,
        "feature_set": "xyv99",
        "exercise_labels": exercise_labels,
        "form_labels": form_labels,
        "participants": {"train": train_p, "val": val_p, "test": test_p},
        "windows": {s: int(arrays[f"X_{s}"].shape[0]) for s in data},
        **stats,
    }
    args.out.with_suffix(".json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
