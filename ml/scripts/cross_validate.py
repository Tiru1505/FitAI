"""Participant-level cross-validation: a fair comparison that does not depend on one lucky split.

Every window of a participant stays in one fold (GroupKFold over participant IDs), so each fold's
test set is made of people the model never trained on. Within each fold's training participants, a
few are held out as an inner validation set for early stopping — the test fold is never used for
model selection.

Model variants:
  baseline    logistic regression on window summary statistics
  bilstm      BiLSTM as trained by train.py defaults
  bilstm_aug  BiLSTM + augmentation (mirror, time-warp, scale, rotate, jitter) + dropout/L2
  gru, gru_aug  the same for GRU

Reports per-fold and mean ± standard deviation macro F1, so "model A beat model B" can be judged
against fold-to-fold variation.

Usage:
    python ml/scripts/cross_validate.py --data ml/data/sequences.npz --folds 5 \
        --models baseline bilstm bilstm_aug --epochs 20
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fitai_ml.data import ML_DIR  # noqa: E402
from fitai_ml.metrics import classification_metrics, save_confusion_matrix_png  # noqa: E402
from train import build_keras_model, class_weights, summary_features  # noqa: E402

VARIANTS = {
    "baseline": {"kind": "baseline"},
    "bilstm": {"kind": "bilstm", "augment": 0, "dropout": 0.3, "recurrent_dropout": 0.0, "l2": 0.0},
    "bilstm_aug": {"kind": "bilstm", "augment": 2, "dropout": 0.5, "recurrent_dropout": 0.25, "l2": 1e-4},
    "gru": {"kind": "gru", "augment": 0, "dropout": 0.3, "recurrent_dropout": 0.0, "l2": 0.0},
    "gru_aug": {"kind": "gru", "augment": 2, "dropout": 0.5, "recurrent_dropout": 0.25, "l2": 1e-4},
}


class Tee:
    def __init__(self, path: Path):
        self.file = path.open("w", encoding="utf-8")

    def write(self, text: str) -> None:
        sys.__stdout__.write(text)
        sys.__stdout__.flush()
        self.file.write(text)
        self.file.flush()

    def close(self) -> None:
        self.file.close()


def pool(data_path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[str]]:
    data = np.load(data_path, allow_pickle=False)
    manifest = json.loads(data_path.with_suffix(".json").read_text(encoding="utf-8"))
    X = np.concatenate([data[f"X_{s}"] for s in ("train", "val", "test")])
    y = np.concatenate([data[f"y_exercise_{s}"] for s in ("train", "val", "test")])
    groups = np.concatenate([data[f"participant_{s}"] for s in ("train", "val", "test")])
    return X, y, groups, manifest["exercise_labels"]


def train_variant(variant: dict, X_tr, y_tr, X_va, y_va, X_te, labels, args, log: Tee):
    started = time.perf_counter()
    if variant["kind"] == "baseline":
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler

        clf = make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, class_weight="balanced"))
        clf.fit(summary_features(X_tr), y_tr)
        return clf.predict(summary_features(X_te)), round(time.perf_counter() - started, 1), len(X_tr), None

    import tensorflow as tf

    from fitai_ml.augment import augment_dataset

    tf.keras.utils.set_random_seed(args.seed)
    if variant["augment"]:
        X_tr, y_tr = augment_dataset(X_tr, y_tr, variant["augment"], args.seed)
    model = build_keras_model(
        variant["kind"], X_tr.shape[1], X_tr.shape[2], len(labels), variant["dropout"], args.lr,
        False, variant["recurrent_dropout"], variant["l2"], args.units,
    )  # fmt: skip
    history = model.fit(
        X_tr, y_tr, validation_data=(X_va, y_va), epochs=args.epochs, batch_size=args.batch_size,
        class_weight=class_weights(y_tr, len(labels)),
        callbacks=[tf.keras.callbacks.EarlyStopping(monitor="val_loss", patience=args.patience, restore_best_weights=True)],
        verbose=0,
    )  # fmt: skip
    epochs_run = len(history.history["loss"])
    log.write(f"      epochs run {epochs_run}, best val loss {min(history.history['val_loss']):.4f}\n")
    return model.predict(X_te, verbose=0).argmax(1), round(time.perf_counter() - started, 1), len(X_tr), epochs_run


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--models", nargs="+", default=["baseline", "bilstm", "bilstm_aug"], choices=list(VARIANTS))
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--units", type=int, default=64)
    parser.add_argument("--patience", type=int, default=5)
    parser.add_argument("--inner-val-participants", type=int, default=2, help="participants held out of training for early stopping")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out-dir", type=Path)
    args = parser.parse_args()

    from sklearn.model_selection import GroupKFold

    started = datetime.now()
    out_dir = args.out_dir or ML_DIR / "results" / f"cross_validation_{started:%Y%m%d_%H%M%S}"
    out_dir.mkdir(parents=True, exist_ok=True)
    log = Tee(out_dir / "execution_log.txt")

    X, y, groups, labels = pool(args.data)
    participants = sorted(set(groups.tolist()))
    log.write(f"Participant-level cross-validation\nstarted {started:%Y-%m-%d %H:%M:%S}\n")
    log.write(f"data: {args.data}\nwindows: {len(X)}  participants: {len(participants)}  classes: {labels}\n")
    log.write(f"folds: {args.folds}  models: {', '.join(args.models)}  epochs: {args.epochs}\n")

    folds = list(GroupKFold(n_splits=args.folds).split(X, y, groups))
    results: dict[str, list[dict]] = {m: [] for m in args.models}
    predictions: dict[str, tuple[list, list]] = {m: ([], []) for m in args.models}
    rng = np.random.default_rng(args.seed)

    for fold, (train_idx, test_idx) in enumerate(folds, start=1):
        test_people = sorted(set(groups[test_idx].tolist()))
        train_people = sorted(set(groups[train_idx].tolist()))
        inner_val = sorted(rng.choice(train_people, size=min(args.inner_val_participants, max(1, len(train_people) - 1)), replace=False).tolist())
        inner_mask = np.isin(groups, inner_val)
        fit_idx = train_idx[~inner_mask[train_idx]]
        val_idx = train_idx[inner_mask[train_idx]]
        log.write(f"\n=== fold {fold}/{len(folds)} ===\n")
        log.write(f"  test participants     : {', '.join(test_people)} ({len(test_idx)} windows)\n")
        log.write(f"  inner val participants: {', '.join(inner_val)} ({len(val_idx)} windows)\n")
        log.write(f"  training windows      : {len(fit_idx)}\n")

        for name in args.models:
            log.write(f"    {name}:\n")
            y_pred, seconds, n_train, epochs_run = train_variant(
                VARIANTS[name], X[fit_idx], y[fit_idx], X[val_idx], y[val_idx], X[test_idx], labels, args, log
            )
            metrics = classification_metrics(y[test_idx], y_pred, labels)
            results[name].append({
                "fold": fold, "test_participants": test_people, "n_test": len(test_idx),
                "n_train": n_train, "seconds": seconds, "epochs_run": epochs_run,
                "accuracy": metrics["accuracy"], "macro_f1": metrics["macro_f1"],
                "macro_precision": metrics["macro_precision"], "macro_recall": metrics["macro_recall"],
            })  # fmt: skip
            predictions[name][0].extend(y[test_idx].tolist())
            predictions[name][1].extend(np.asarray(y_pred).tolist())
            log.write(f"      macro F1 {metrics['macro_f1']:.4f}  accuracy {metrics['accuracy']:.4f}  ({seconds}s)\n")

    log.write("\n" + "=" * 78 + "\nCross-validated results (mean +/- sd over folds)\n" + "=" * 78 + "\n")
    summary = {}
    for name in args.models:
        f1s = [r["macro_f1"] for r in results[name]]
        accs = [r["accuracy"] for r in results[name]]
        summary[name] = {
            "macro_f1_mean": round(statistics.mean(f1s), 4),
            "macro_f1_sd": round(statistics.stdev(f1s), 4) if len(f1s) > 1 else 0.0,
            "macro_f1_per_fold": f1s,
            "accuracy_mean": round(statistics.mean(accs), 4),
            "accuracy_sd": round(statistics.stdev(accs), 4) if len(accs) > 1 else 0.0,
            "total_seconds": round(sum(r["seconds"] for r in results[name]), 1),
        }
        log.write(f"{name:<12} macro F1 {summary[name]['macro_f1_mean']:.4f} +/- {summary[name]['macro_f1_sd']:.4f}   "
                  f"accuracy {summary[name]['accuracy_mean']:.4f} +/- {summary[name]['accuracy_sd']:.4f}   "
                  f"per fold {[round(v, 3) for v in f1s]}\n")  # fmt: skip
        pooled = classification_metrics(predictions[name][0], predictions[name][1], labels)
        save_confusion_matrix_png(pooled["confusion_matrix"], labels, out_dir / f"{name}_confusion_matrix.png",
                                  f"{name} - pooled across {len(folds)} folds")  # fmt: skip
        summary[name]["pooled_per_class"] = pooled["per_class"]
        summary[name]["pooled_confusion_matrix"] = pooled["confusion_matrix"]

    best = max(summary, key=lambda k: summary[k]["macro_f1_mean"])
    log.write(f"\nbest mean macro F1: {best} ({summary[best]['macro_f1_mean']})\n")

    (out_dir / "cv_results.json").write_text(json.dumps({"summary": summary, "folds": results, "labels": labels}, indent=2), encoding="utf-8")

    rows = ["| Model | Mean macro F1 | SD | Per-fold macro F1 | Mean accuracy | Total train time (s) |", "|---|---|---|---|---|---|"]
    for name in args.models:
        s = summary[name]
        rows.append(f"| {name} | **{s['macro_f1_mean']}** | {s['macro_f1_sd']} | {[round(v, 3) for v in s['macro_f1_per_fold']]} | {s['accuracy_mean']} | {s['total_seconds']} |")
    fold_lines = "\n".join(
        f"| {r['fold']} | {', '.join(r['test_participants'])} | {r['n_test']} | " +
        " | ".join(f"{next(x['macro_f1'] for x in results[m] if x['fold'] == r['fold'])}" for m in args.models) + " |"
        for r in results[args.models[0]]
    )
    (out_dir / "RESULTS.md").write_text(f"""# Participant-level cross-validation — {started:%Y-%m-%d %H:%M}

{args.folds}-fold GroupKFold over {len(participants)} participants ({len(X)} windows). Every window of a
participant stays in one fold, and {args.inner_val_participants} training participants are held out
inside each fold for early stopping, so the test fold is never used for model selection.

## Summary

{chr(10).join(rows)}

Best mean macro F1: **{best}** ({summary[best]['macro_f1_mean']} ± {summary[best]['macro_f1_sd']}).

## Per-fold macro F1

| Fold | Test participants | Test windows | {' | '.join(args.models)} |
|---|---|---|{'---|' * len(args.models)}
{fold_lines}

## Notes

- `*_aug` variants add mirroring, time-warping, scaling, rotation and jitter, with dropout 0.5,
  recurrent dropout 0.25 and L2 1e-4.
- Compare the gap between models against the SD across folds: a difference smaller than the SD is
  not evidence that one model is better.
- Confusion matrices pooled over all folds: `<model>_confusion_matrix.png`.
- Full log: `execution_log.txt`; raw numbers: `cv_results.json`.
""", encoding="utf-8")

    log.write(f"\nDone in {(datetime.now() - started).total_seconds() / 60:.1f} min.\nEvidence: {out_dir}\n")
    log.close()


if __name__ == "__main__":
    main()
