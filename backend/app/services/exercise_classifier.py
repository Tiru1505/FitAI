"""Loads trained sequence classifiers (BiLSTM / GRU) exported by ``ml/scripts/train.py``.

Expected files in ``trained_models/``:

    exercise_classifier.keras        + exercise_classifier.meta.json
    form_classifier_<exercise>.keras + form_classifier_<exercise>.meta.json   (optional)

TensorFlow is an optional dependency. If it is not installed, or no model files
exist, the registry reports the models as unavailable and the API says so
explicitly instead of producing predictions.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from app.services import pose_service as ps

logger = logging.getLogger("fitai.classifier")


@dataclass
class Prediction:
    label: str
    confidence: float
    probabilities: dict[str, float]


@dataclass
class SequenceClassifier:
    name: str
    model_path: Path
    meta_path: Path
    available: bool = False
    status: str = "not loaded"
    labels: list[str] = field(default_factory=list)
    sequence_length: int = 60
    model_type: str | None = None
    _model: object | None = None

    def load(self) -> None:
        if not self.model_path.exists() or not self.meta_path.exists():
            self.status = "model file not found; train and export a model first"
            return
        try:
            meta = json.loads(self.meta_path.read_text(encoding="utf-8"))
            if meta.get("feature_set") != ps.FEATURE_SET:
                self.status = f"incompatible feature_set {meta.get('feature_set')!r}"
                return
            self.labels = list(meta["labels"])
            self.sequence_length = int(meta["sequence_length"])
            self.model_type = meta.get("model_type")
        except (OSError, ValueError, KeyError) as exc:
            self.status = f"invalid metadata: {exc}"
            return
        try:
            import tensorflow as tf  # noqa: PLC0415 - optional heavy dependency
        except ImportError:
            self.status = "tensorflow is not installed (pip install -r requirements-ml.txt)"
            return
        try:
            model = tf.keras.models.load_model(self.model_path, compile=False)
            # A compiled graph with a fixed signature is ~100x faster than eager calls for single windows.
            self._model = tf.function(
                lambda x: model(x, training=False),
                input_signature=[tf.TensorSpec([1, self.sequence_length, ps.FEATURES_PER_FRAME], tf.float32)],
            )
            self._model(np.zeros((1, self.sequence_length, ps.FEATURES_PER_FRAME), np.float32))  # warm-up trace
        except Exception as exc:  # noqa: BLE001 - surface any load failure as status
            logger.exception("failed to load %s", self.model_path.name)
            self.status = f"failed to load model: {exc.__class__.__name__}"
            return
        self.available = True
        self.status = "loaded"
        logger.info("loaded %s (%s, %d labels)", self.name, self.model_type, len(self.labels))

    def predict(self, window: np.ndarray) -> Prediction | None:
        """window: [sequence_length, 99] feature array."""
        if not self.available or self._model is None or window.shape[0] != self.sequence_length:
            return None
        probs = np.asarray(self._model(window[np.newaxis, ...].astype(np.float32)))[0]
        best = int(np.argmax(probs))
        return Prediction(
            label=self.labels[best],
            confidence=float(probs[best]),
            probabilities={label: round(float(p), 4) for label, p in zip(self.labels, probs)},
        )

    def describe(self) -> dict:
        return {
            "available": self.available,
            "status": self.status,
            "model_type": self.model_type,
            "labels": self.labels,
            "sequence_length": self.sequence_length if self.available else None,
        }


class ModelRegistry:
    def __init__(self, models_dir: Path, exercises: tuple[str, ...]):
        self.models_dir = models_dir
        self.exercise_classifier = SequenceClassifier(
            "exercise_classifier",
            models_dir / "exercise_classifier.keras",
            models_dir / "exercise_classifier.meta.json",
        )
        self.form_classifiers = {
            ex: SequenceClassifier(
                f"form_classifier_{ex}",
                models_dir / f"form_classifier_{ex}.keras",
                models_dir / f"form_classifier_{ex}.meta.json",
            )
            for ex in exercises
        }

    def load_all(self) -> None:
        self.exercise_classifier.load()
        for clf in self.form_classifiers.values():
            clf.load()

    def status(self) -> dict:
        return {
            "exercise_classifier": self.exercise_classifier.describe(),
            "form_classifiers": {ex: clf.describe() for ex, clf in self.form_classifiers.items()},
        }
