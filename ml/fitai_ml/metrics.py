from __future__ import annotations

import numpy as np
from sklearn.metrics import accuracy_score, confusion_matrix, precision_recall_fscore_support


def classification_metrics(y_true, y_pred, labels: list[str]) -> dict:
    idx = list(range(len(labels)))
    p, r, f1, support = precision_recall_fscore_support(y_true, y_pred, labels=idx, zero_division=0)
    mp, mr, mf1, _ = precision_recall_fscore_support(y_true, y_pred, labels=idx, average="macro", zero_division=0)
    return {
        "n": int(len(y_true)),
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4) if len(y_true) else None,
        "macro_precision": round(float(mp), 4),
        "macro_recall": round(float(mr), 4),
        "macro_f1": round(float(mf1), 4),
        "per_class": {
            labels[i]: {"precision": round(float(p[i]), 4), "recall": round(float(r[i]), 4), "f1": round(float(f1[i]), 4), "support": int(support[i])}
            for i in idx
        },
        "labels": labels,
        "confusion_matrix": confusion_matrix(y_true, y_pred, labels=idx).tolist(),
    }


def save_confusion_matrix_png(cm: list[list[int]], labels: list[str], path, title: str) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    arr = np.asarray(cm)
    fig, ax = plt.subplots(figsize=(1.2 * len(labels) + 2, 1.1 * len(labels) + 1.5))
    ax.imshow(arr, cmap="Blues")
    ax.set_xticks(range(len(labels)), labels, rotation=45, ha="right")
    ax.set_yticks(range(len(labels)), labels)
    ax.set_xlabel("Predicted")
    ax.set_ylabel("True")
    ax.set_title(title)
    threshold = arr.max() / 2 if arr.size else 0
    for i in range(arr.shape[0]):
        for j in range(arr.shape[1]):
            ax.text(j, i, int(arr[i, j]), ha="center", va="center", color="white" if arr[i, j] > threshold else "black")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
