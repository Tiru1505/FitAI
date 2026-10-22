"""Evaluate a trained run on the held-out TEST participants and measure inference latency.

Usage:
  python ml/scripts/evaluate.py --data ml/data/sequences.npz --run ml/results/exercise_classifier_bilstm_YYYYMMDD_HHMMSS

Writes test_metrics.json and confusion_matrix.png into the run directory. These measured
numbers are what should be copied into docs/EVALUATION_REPORT.md.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fitai_ml.metrics import classification_metrics, save_confusion_matrix_png  # noqa: E402
from train import load_task, summary_features  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--latency-trials", type=int, default=200)
    args = parser.parse_args()

    config = json.loads((args.run / "config.json").read_text(encoding="utf-8"))
    splits, labels, _ = load_task(args.data, config["task"], config.get("exercise"))
    X_te, y_te = splits["test"]
    if len(X_te) == 0:
        raise SystemExit("test split is empty")
    if labels != config["labels"]:
        raise SystemExit("label set in data does not match the trained run")

    if config["model"] == "baseline":
        import joblib

        clf = joblib.load(args.run / "baseline.joblib")["model"]
        predict_one = lambda w: clf.predict(summary_features(w[np.newaxis]))  # noqa: E731
        y_pred = clf.predict(summary_features(X_te))
    else:
        import tensorflow as tf

        name = "exercise_classifier" if config["task"] == "exercise" else f"form_classifier_{config['exercise']}"
        model = tf.keras.models.load_model(args.run / f"{name}.keras", compile=False)
        infer = tf.function(lambda x: model(x, training=False), input_signature=[tf.TensorSpec([1, *X_te.shape[1:]], tf.float32)])
        predict_one = lambda w: infer(w[np.newaxis].astype(np.float32)).numpy()  # noqa: E731
        y_pred = model.predict(X_te, verbose=0).argmax(1)

    metrics = classification_metrics(y_te, y_pred, labels)
    metrics["test_participants"] = config["participants"]["test"]

    for _ in range(10):  # warm-up
        predict_one(X_te[0])
    timings = []
    for i in range(args.latency_trials):
        start = time.perf_counter()
        predict_one(X_te[i % len(X_te)])
        timings.append((time.perf_counter() - start) * 1000)
    metrics["latency_ms_per_window"] = {
        "mean": round(float(np.mean(timings)), 3),
        "p50": round(float(np.percentile(timings, 50)), 3),
        "p95": round(float(np.percentile(timings, 95)), 3),
        "trials": args.latency_trials,
    }

    (args.run / "test_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    save_confusion_matrix_png(metrics["confusion_matrix"], labels, args.run / "confusion_matrix.png", f"{config['model']} - test participants")
    print(json.dumps({k: metrics[k] for k in ("n", "accuracy", "macro_precision", "macro_recall", "macro_f1", "latency_ms_per_window")}, indent=2))


if __name__ == "__main__":
    main()
