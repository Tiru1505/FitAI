"""Train an exercise or form classifier on windows produced by build_sequences.py.

Models:
  bilstm   (primary)  BiLSTM(64) -> Dropout -> BiLSTM(32) -> Dropout -> Dense(32, relu) -> Softmax
  gru      (comparison) same topology with bidirectional GRU layers
  baseline logistic regression on per-window summary statistics (mean/std/min/max)

Windows are fixed-length (no padding), so no Masking layer is needed. Class imbalance is
handled with class weights (default) or focal loss (--focal-loss).

Examples:
  python ml/scripts/train.py --data ml/data/sequences.npz --task exercise --model bilstm --export
  python ml/scripts/train.py --data ml/data/sequences.npz --task form --exercise squat --model gru
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fitai_ml.data import ML_DIR, TRAINED_MODELS_DIR  # noqa: E402
from fitai_ml.metrics import classification_metrics  # noqa: E402


def load_task(data_path: Path, task: str, exercise: str | None):
    data = np.load(data_path, allow_pickle=False)
    manifest = json.loads(data_path.with_suffix(".json").read_text(encoding="utf-8"))
    splits = {}
    for split in ("train", "val", "test"):
        X, y = data[f"X_{split}"], data[f"y_{task}_{split}"]
        if task == "form":
            mask = data[f"exercise_name_{split}"] == exercise
            X, y = X[mask], y[mask]
        splits[split] = (X, y)
    labels = manifest["exercise_labels"] if task == "exercise" else manifest["form_labels"]
    if task == "form":
        # Keep only form labels that occur for this exercise, and re-index them.
        present = sorted({int(v) for _, y in splits.values() for v in y})
        remap = {old: new for new, old in enumerate(present)}
        labels = [labels[i] for i in present]
        splits = {s: (X, np.asarray([remap[int(v)] for v in y], dtype=np.int64)) for s, (X, y) in splits.items()}
    return splits, labels, manifest


def class_weights(y: np.ndarray, n_classes: int) -> dict[int, float]:
    counts = np.bincount(y, minlength=n_classes).astype(float)
    weights = len(y) / (n_classes * np.maximum(counts, 1))
    return {i: float(w) for i, w in enumerate(weights)}


def summary_features(X: np.ndarray) -> np.ndarray:
    return np.concatenate([X.mean(1), X.std(1), X.min(1), X.max(1)], axis=1)


def build_keras_model(kind: str, seq_len: int, n_features: int, n_classes: int, dropout: float, lr: float,
                      focal: bool, recurrent_dropout: float = 0.0, l2: float = 0.0, units: int = 64):
    import tensorflow as tf
    from tensorflow.keras import layers, regularizers

    rnn = layers.LSTM if kind == "bilstm" else layers.GRU
    reg = regularizers.l2(l2) if l2 else None
    model = tf.keras.Sequential(
        [
            layers.Input(shape=(seq_len, n_features)),
            layers.Bidirectional(rnn(units, return_sequences=True, recurrent_dropout=recurrent_dropout, kernel_regularizer=reg)),
            layers.Dropout(dropout),
            layers.Bidirectional(rnn(max(8, units // 2), recurrent_dropout=recurrent_dropout, kernel_regularizer=reg)),
            layers.Dropout(dropout),
            layers.Dense(32, activation="relu", kernel_regularizer=reg),
            layers.Dense(n_classes, activation="softmax"),
        ]
    )
    if focal:
        def sparse_focal_loss(y_true, y_pred, gamma=2.0):
            y_true = tf.cast(tf.reshape(y_true, [-1]), tf.int32)
            p_t = tf.gather(y_pred, y_true, axis=1, batch_dims=1)
            p_t = tf.clip_by_value(p_t, 1e-7, 1.0)
            return -tf.pow(1.0 - p_t, gamma) * tf.math.log(p_t)

        loss = sparse_focal_loss
    else:
        loss = "sparse_categorical_crossentropy"  # categorical cross-entropy with integer labels
    model.compile(optimizer=tf.keras.optimizers.Adam(lr), loss=loss, metrics=["accuracy"])
    return model


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--task", choices=["exercise", "form"], required=True)
    parser.add_argument("--exercise", help="required for --task form")
    parser.add_argument("--model", choices=["bilstm", "gru", "baseline"], default="bilstm")
    parser.add_argument("--epochs", type=int, default=60)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--dropout", type=float, default=0.3)
    parser.add_argument("--recurrent-dropout", type=float, default=0.0)
    parser.add_argument("--l2", type=float, default=0.0, help="L2 weight decay on kernels")
    parser.add_argument("--units", type=int, default=64, help="units in the first recurrent layer")
    parser.add_argument("--augment", type=int, default=0, metavar="N",
                        help="add N augmented copies of the training set (mirror, time-warp, scale, rotate, jitter)")
    parser.add_argument("--patience", type=int, default=10)
    parser.add_argument("--focal-loss", action="store_true")
    parser.add_argument("--no-class-weights", action="store_true")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--export", action="store_true", help="copy the trained model into backend/trained_models")
    args = parser.parse_args()
    if args.task == "form" and not args.exercise:
        parser.error("--exercise is required for --task form")

    splits, labels, manifest = load_task(args.data, args.task, args.exercise)
    (X_tr, y_tr), (X_va, y_va), (X_te, _) = splits["train"], splits["val"], splits["test"]
    if len(X_tr) == 0 or len(X_va) == 0:
        raise SystemExit("train and validation splits must both contain windows")
    if len(labels) < 2:
        raise SystemExit(f"need at least 2 classes, found {labels}")

    name = "exercise_classifier" if args.task == "exercise" else f"form_classifier_{args.exercise}"
    run_dir = ML_DIR / "results" / f"{name}_{args.model}_{datetime.now():%Y%m%d_%H%M%S}"
    run_dir.mkdir(parents=True, exist_ok=True)
    np.random.seed(args.seed)
    config = {**vars(args), "data": str(args.data), "labels": labels, "sequence_length": int(X_tr.shape[1]),
              "train_windows": int(len(X_tr)), "val_windows": int(len(X_va)), "test_windows": int(len(X_te)),
              "participants": manifest["participants"]}  # fmt: skip

    if args.augment and args.model != "baseline":
        from fitai_ml.augment import augment_dataset

        before = len(X_tr)
        X_tr, y_tr = augment_dataset(X_tr, y_tr, args.augment, args.seed)
        print(f"augmentation: {before} -> {len(X_tr)} training windows ({args.augment} augmented copies)")
        config["train_windows_after_augmentation"] = int(len(X_tr))

    if args.model == "baseline":
        import joblib
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler

        clf = make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, class_weight=None if args.no_class_weights else "balanced"))
        started = time.perf_counter()
        clf.fit(summary_features(X_tr), y_tr)
        config["train_seconds"] = round(time.perf_counter() - started, 2)
        val_pred = clf.predict(summary_features(X_va))
        joblib.dump({"model": clf, "labels": labels}, run_dir / "baseline.joblib")
        history = {}
    else:
        import tensorflow as tf

        tf.keras.utils.set_random_seed(args.seed)
        model = build_keras_model(args.model, X_tr.shape[1], X_tr.shape[2], len(labels), args.dropout, args.lr,
                                  args.focal_loss, args.recurrent_dropout, args.l2, args.units)
        callbacks = [tf.keras.callbacks.EarlyStopping(monitor="val_loss", patience=args.patience, restore_best_weights=True)]
        started = time.perf_counter()
        fit = model.fit(
            X_tr, y_tr, validation_data=(X_va, y_va), epochs=args.epochs, batch_size=args.batch_size,
            class_weight=None if (args.no_class_weights or args.focal_loss) else class_weights(y_tr, len(labels)),
            callbacks=callbacks, verbose=2,
        )  # fmt: skip
        config["train_seconds"] = round(time.perf_counter() - started, 2)
        config["epochs_run"] = len(fit.history["loss"])
        history = {k: [round(float(v), 5) for v in vals] for k, vals in fit.history.items()}
        val_pred = model.predict(X_va, verbose=0).argmax(1)
        model.save(run_dir / f"{name}.keras")
        meta = {
            "name": name,
            "model_type": args.model,
            "feature_set": "xyv99",
            "normalization": "hip_center_body_scale",
            "sequence_length": int(X_tr.shape[1]),
            "labels": labels,
            "trained_at": datetime.now().isoformat(timespec="seconds"),
            "run_dir": str(run_dir),
        }
        (run_dir / f"{name}.meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        if args.export:
            TRAINED_MODELS_DIR.mkdir(parents=True, exist_ok=True)
            model.save(TRAINED_MODELS_DIR / f"{name}.keras")
            (TRAINED_MODELS_DIR / f"{name}.meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
            print(f"exported to {TRAINED_MODELS_DIR}")

    val_metrics = classification_metrics(y_va, val_pred, labels)
    (run_dir / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    (run_dir / "history.json").write_text(json.dumps(history, indent=2), encoding="utf-8")
    (run_dir / "val_metrics.json").write_text(json.dumps(val_metrics, indent=2), encoding="utf-8")
    print(f"validation macro F1 = {val_metrics['macro_f1']}  accuracy = {val_metrics['accuracy']}")
    print(f"run saved to {run_dir}")


if __name__ == "__main__":
    main()
