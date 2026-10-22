"""Explainable repetition counting: joint angle -> moving average -> finite-state machine.

A repetition is counted only when the phases occur in order:

    start -> descending -> bottom -> ascending -> complete (back to start)

"descending" / "bottom" are generic names for "moving toward the target angle" and
"target angle reached". For a shoulder press the target is arms extended overhead,
so "descending" means pressing upward; the logic is identical with the thresholds
mirrored (``start_is_high=False``).

If the movement returns to the start position without reaching the target, a
partial repetition is recorded instead of a full one. The state resets when the
required landmarks are not visible for several consecutive frames.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import numpy as np

from app.services import pose_service as ps


@dataclass(frozen=True)
class RepConfig:
    exercise: str
    joints: tuple[str, str, str]
    # How to combine left/right sides: "best_visibility" | "min" | "mean"
    side_mode: str
    start_is_high: bool
    start_threshold: float
    target_threshold: float
    hysteresis: float = 8.0
    smoothing_window: int = 5


REP_CONFIGS: dict[str, RepConfig] = {
    "squat": RepConfig("squat", ("hip", "knee", "ankle"), "best_visibility", True, 160.0, 100.0),
    "lunge": RepConfig("lunge", ("hip", "knee", "ankle"), "min", True, 160.0, 105.0),
    "push_up": RepConfig("push_up", ("shoulder", "elbow", "wrist"), "best_visibility", True, 150.0, 95.0),
    "biceps_curl": RepConfig("biceps_curl", ("shoulder", "elbow", "wrist"), "min", True, 150.0, 65.0),
    "shoulder_press": RepConfig("shoulder_press", ("shoulder", "elbow", "wrist"), "mean", False, 105.0, 155.0),
}

PHASES = ("not_started", "start", "descending", "bottom", "ascending", "complete")


@dataclass
class RepUpdate:
    visible: bool
    angle: float | None
    phase: str
    repetition_count: int
    partial_count: int
    rep_completed: bool = False
    partial_rep: bool = False
    rep_extreme_angle: float | None = None


def combined_angle(arr: np.ndarray, config: RepConfig, min_visibility: float) -> float | None:
    """Joint angle for the exercise, combining sides as configured. None when not visible."""
    sides = []
    for side in ("left", "right"):
        angle, vis = ps.side_angle(arr, side, config.joints)
        if vis >= min_visibility and np.isfinite(angle):
            sides.append((angle, vis))
    if not sides:
        return None
    if config.side_mode == "best_visibility":
        return max(sides, key=lambda s: s[1])[0]
    angles = [s[0] for s in sides]
    if config.side_mode == "min":
        return min(angles) if config.start_is_high else max(angles)
    return float(np.mean(angles))


@dataclass
class RepCounter:
    config: RepConfig
    min_visibility: float = 0.5
    invisible_frames_before_reset: int = 15

    count: int = 0
    partial_count: int = 0
    state: str = "not_started"
    _window: deque = field(default_factory=deque)
    _invisible_frames: int = 0
    _extreme: float | None = None

    # --- threshold helpers (mirrored when start_is_high is False) -----------
    def _in_start(self, a: float) -> bool:
        c = self.config
        return a >= c.start_threshold if c.start_is_high else a <= c.start_threshold

    def _in_target(self, a: float) -> bool:
        c = self.config
        return a <= c.target_threshold if c.start_is_high else a >= c.target_threshold

    def _left_start(self, a: float) -> bool:
        c = self.config
        return a < c.start_threshold - c.hysteresis if c.start_is_high else a > c.start_threshold + c.hysteresis

    def _left_target(self, a: float) -> bool:
        c = self.config
        return a > c.target_threshold + c.hysteresis if c.start_is_high else a < c.target_threshold - c.hysteresis

    def _track_extreme(self, a: float) -> None:
        if self._extreme is None:
            self._extreme = a
        else:
            self._extreme = min(self._extreme, a) if self.config.start_is_high else max(self._extreme, a)

    def reset_state(self) -> None:
        self.state = "not_started"
        self._window.clear()
        self._extreme = None

    def update_angle(self, raw_angle: float | None) -> RepUpdate:
        """Advance the state machine with one raw angle sample (None = not visible)."""
        if raw_angle is None:
            self._invisible_frames += 1
            if self._invisible_frames >= self.invisible_frames_before_reset:
                self.reset_state()
            return RepUpdate(False, None, self.state, self.count, self.partial_count)

        self._invisible_frames = 0
        self._window.append(raw_angle)
        while len(self._window) > self.config.smoothing_window:
            self._window.popleft()
        a = float(np.mean(self._window))

        completed = partial = False
        extreme = None
        s = self.state

        if s in ("not_started", "complete"):
            s = "start" if self._in_start(a) else "not_started"
        if s == "start":
            if self._left_start(a):
                s = "descending"
                self._extreme = a
        elif s == "descending":
            self._track_extreme(a)
            if self._in_target(a):
                s = "bottom"
            elif self._in_start(a):
                self.partial_count += 1
                partial, extreme = True, self._extreme
                s, self._extreme = "start", None
        elif s == "bottom":
            self._track_extreme(a)
            if self._left_target(a):
                s = "ascending"
        elif s == "ascending":
            if self._in_start(a):
                self.count += 1
                completed, extreme = True, self._extreme
                s, self._extreme = "complete", None
            elif self._in_target(a):
                s = "bottom"

        self.state = s
        return RepUpdate(True, a, s, self.count, self.partial_count, completed, partial, extreme)

    def update(self, arr: np.ndarray) -> RepUpdate:
        """Advance with an aspect-corrected landmark frame (33 x 4)."""
        return self.update_angle(combined_angle(arr, self.config, self.min_visibility))


def make_rep_counter(exercise: str, min_visibility: float = 0.5, invisible_frames_before_reset: int = 15) -> RepCounter:
    if exercise not in REP_CONFIGS:
        raise ValueError(f"unsupported exercise: {exercise}")
    return RepCounter(REP_CONFIGS[exercise], min_visibility, invisible_frames_before_reset)
