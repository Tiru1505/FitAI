"""Per-stream analysis pipeline used by the WebSocket and the REST sequence analyzer.

frame -> aspect correction -> rep counter (FSM) -> rule-based form checks
      -> (every N frames, once a full window is buffered) BiLSTM exercise / form models
"""

from __future__ import annotations

import time
from collections import deque

import numpy as np

from app.core.config import Settings
from app.services import pose_service as ps
from app.services.exercise_classifier import ModelRegistry, Prediction
from app.services.form_feedback import FormAnalyzer, message_for
from app.services.rep_counter import CalibrationSettings, make_rep_counter

CORRECT_FORM_LABELS = {"correct", "good", "correct_form"}


class LiveAnalyzer:
    def __init__(self, expected_exercise: str, registry: ModelRegistry, settings: Settings):
        self.expected_exercise = expected_exercise
        self.registry = registry
        self.settings = settings
        self.rep_counter = make_rep_counter(
            expected_exercise,
            settings.min_landmark_visibility,
            settings.invisible_frames_before_reset,
            CalibrationSettings(
                enabled=settings.calibrate_rep_counter,
                warmup_samples=settings.calibration_warmup_samples,
                min_range_degrees=settings.calibration_min_range_degrees,
                start_fraction=settings.calibration_start_fraction,
                target_fraction=settings.calibration_target_fraction,
            ),
        )
        self.form = FormAnalyzer(expected_exercise, settings.min_landmark_visibility)
        self.features: deque[np.ndarray] = deque(maxlen=settings.sequence_length)
        self.frames = 0
        self.visible_frames = 0
        self.processing_ms_total = 0.0
        self.last_exercise_pred: Prediction | None = None
        self.last_form_pred: Prediction | None = None
        self.exercise_votes: dict[str, int] = {}
        self.model_form_counts: dict[str, int] = {}

    def process(
        self, landmarks: list[list[float]] | None, image_width: float | None = None, image_height: float | None = None
    ) -> dict:
        started = time.perf_counter()
        self.frames += 1
        arr = None
        if landmarks is not None:
            arr = ps.aspect_corrected(ps.to_array(landmarks), image_width, image_height)

        rep = self.rep_counter.update(arr) if arr is not None else self.rep_counter.update_angle(None)
        frame_form = self.form.update(arr if rep.visible else None, rep)

        if rep.visible and arr is not None:
            self.visible_frames += 1
            self.features.append(ps.frame_features(arr))
        elif self.rep_counter.state == "not_started":
            self.features.clear()

        self._maybe_classify()
        message = self._build_message(rep, frame_form)
        elapsed = (time.perf_counter() - started) * 1000
        self.processing_ms_total += elapsed
        message["processing_ms"] = round(elapsed, 2)
        return message

    def _maybe_classify(self) -> None:
        n = self.settings.sequence_length
        if len(self.features) < n or self.frames % self.settings.classify_every_n_frames:
            return
        window = np.stack(self.features)
        clf = self.registry.exercise_classifier
        if clf.available and clf.sequence_length == n:
            self.last_exercise_pred = clf.predict(window)
            if self.last_exercise_pred and self.last_exercise_pred.confidence >= self.settings.classifier_confidence_threshold:
                label = self.last_exercise_pred.label
                self.exercise_votes[label] = self.exercise_votes.get(label, 0) + 1
        form_clf = self.registry.form_classifiers.get(self.expected_exercise)
        if form_clf and form_clf.available and form_clf.sequence_length == n:
            self.last_form_pred = form_clf.predict(window)
            if self.last_form_pred and self.last_form_pred.confidence >= self.settings.classifier_confidence_threshold:
                label = self.last_form_pred.label
                self.model_form_counts[label] = self.model_form_counts.get(label, 0) + 1

    def _build_message(self, rep, frame_form) -> dict:
        threshold = self.settings.classifier_confidence_threshold
        clf_available = self.registry.exercise_classifier.available

        exercise, confidence, source = self.expected_exercise, None, "user_selected"
        feedback, form_status = frame_form.feedback, frame_form.status
        form_source = "rules"

        pred = self.last_exercise_pred
        if clf_available:
            if pred is None:
                exercise, source = "collecting_frames", "model"
            else:
                confidence, source = round(pred.confidence, 3), "model"
                if pred.confidence < threshold:
                    exercise = "uncertain"
                else:
                    exercise = pred.label
                    if rep.visible and pred.label != self.expected_exercise:
                        feedback = (
                            f"This looks like {pred.label.replace('_', ' ')}, but "
                            f"{self.expected_exercise.replace('_', ' ')} was selected. Reps are counted for the selected exercise."
                        )

        form_pred = self.last_form_pred
        if rep.visible and form_pred and form_pred.confidence >= threshold:
            form_source = "model+rules"
            if form_pred.label not in CORRECT_FORM_LABELS and form_status in ("good", "not_started"):
                form_status = "minor_error"
                feedback = message_for(form_pred.label)

        return {
            "type": "analysis",
            "expected_exercise": self.expected_exercise,
            "exercise": exercise,
            "confidence": confidence,
            "recognition_source": source,
            "repetition_count": rep.repetition_count,
            "partial_repetitions": rep.partial_count,
            "phase": rep.phase,
            "angle": round(rep.angle, 1) if rep.angle is not None else None,
            "form_status": form_status,
            "form_source": form_source,
            "active_errors": frame_form.active_errors,
            "feedback": feedback,
            "visible": rep.visible,
            "calibrated": rep.calibrated,
            "form_score": self.form.summary()["form_score"],
        }

    def summary(self) -> dict:
        form = self.form.summary()
        for label, count in self.model_form_counts.items():
            if label not in CORRECT_FORM_LABELS:
                form["error_counts"].setdefault(f"model:{label}", count)
        return {
            "exercise": self.expected_exercise,
            "calibrated": self.rep_counter.calibrated,
            "calibrated_thresholds": (
                {"start": self.rep_counter.config.start_threshold, "target": self.rep_counter.config.target_threshold}
                if self.rep_counter.calibrated else None
            ),
            "repetitions": self.rep_counter.count,
            "partial_repetitions": self.rep_counter.partial_count,
            **form,
            "frames": self.frames,
            "visible_frames": self.visible_frames,
            "low_visibility_ratio": round(1 - self.visible_frames / self.frames, 4) if self.frames else None,
            "avg_processing_ms": round(self.processing_ms_total / self.frames, 3) if self.frames else None,
            "model_exercise_votes": self.exercise_votes,
        }
