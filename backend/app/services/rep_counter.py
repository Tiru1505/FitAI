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
from dataclasses import dataclass, field, replace

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


@dataclass(frozen=True)
class CalibrationSettings:
    """How the counter learns thresholds from the user instead of using fixed angles.

    A fixed depth threshold assumes a camera position. Seen head-on, a knee angle is
    foreshortened and a genuinely deep squat may never read below 100 degrees, so reps are
    missed; seen side-on the same threshold is correct. Measuring the person's own range of
    motion and placing the thresholds inside it removes that assumption, and adapts to body
    proportions and mobility at the same time.
    """

    enabled: bool = True
    # Samples of a visible joint angle to observe before thresholds are derived.
    warmup_samples: int = 45
    # Calibration is refused below this range, so a stationary or barely moving person
    # cannot produce thresholds a twitch would satisfy.
    min_range_degrees: float = 25.0
    # Where the thresholds sit inside the observed range, as fractions of it.
    start_fraction: float = 0.15  # distance in from the resting end
    target_fraction: float = 0.35  # distance in from the far end
    # Percentiles used for the range, so a single bad frame cannot define it.
    low_percentile: float = 5.0
    high_percentile: float = 95.0
    history: int = 450  # rolling window of angles kept for recalibration (~30 s at 15 fps)


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
    calibrated: bool = False


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
    calibration: CalibrationSettings = field(default_factory=CalibrationSettings)

    count: int = 0
    partial_count: int = 0
    state: str = "not_started"
    calibrated: bool = False
    _window: deque = field(default_factory=deque)
    _invisible_frames: int = 0
    _extreme: float | None = None
    _history: deque = field(default_factory=deque)
    _replay: deque = field(default_factory=deque)
    _default_config: RepConfig | None = None

    def __post_init__(self) -> None:
        self._default_config = self.config
        self._history = deque(maxlen=self.calibration.history)
        self._replay = deque(maxlen=self.calibration.history)

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
        # An interrupted repetition must not be recovered by a later replay.
        self._replay.clear()

    def _calibrate(self) -> None:
        """Derive thresholds from the angles seen so far, if the movement is wide enough.

        Only called while the user is between repetitions, so thresholds never move
        underneath an in-progress rep.
        """
        cal = self.calibration
        if len(self._history) < cal.warmup_samples:
            return
        angles = np.fromiter(self._history, dtype=np.float64)
        low = float(np.percentile(angles, cal.low_percentile))
        high = float(np.percentile(angles, cal.high_percentile))
        span = high - low
        if span < cal.min_range_degrees:
            return  # too little movement to tell a repetition from noise

        base = self._default_config or self.config
        if base.start_is_high:
            start = high - cal.start_fraction * span
            target = low + cal.target_fraction * span
        else:
            start = low + cal.start_fraction * span
            target = high - cal.target_fraction * span
        self.config = replace(
            base,
            start_threshold=round(start, 1),
            target_threshold=round(target, 1),
            hysteresis=round(max(4.0, 0.08 * span), 1),
        )
        if not self.calibrated:
            # The warm-up repetitions were judged against thresholds that may not have fitted
            # this person or camera angle. Replay the buffered angles through the new ones so
            # the user is not silently short-changed for the reps they actually did.
            replay = RepCounter(self.config, self.min_visibility, self.invisible_frames_before_reset,
                                CalibrationSettings(enabled=False))  # fmt: skip
            for angle in self._replay:
                replay.update_angle(angle)
            self.count, self.partial_count = replay.count, replay.partial_count
            self.state, self._extreme = replay.state, replay._extreme
            self._window = replay._window
        self.calibrated = True

    def update_angle(self, raw_angle: float | None) -> RepUpdate:
        """Advance the state machine with one raw angle sample (None = not visible)."""
        if raw_angle is None:
            self._invisible_frames += 1
            if self._invisible_frames >= self.invisible_frames_before_reset:
                self.reset_state()
            return RepUpdate(False, None, self.state, self.count, self.partial_count)

        self._invisible_frames = 0
        self._history.append(raw_angle)
        self._replay.append(raw_angle)
        # Recalibrate only while idle or at rest: never mid-repetition.
        if self.calibration.enabled and self.state in ("not_started", "start", "complete"):
            self._calibrate()
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
        return RepUpdate(True, a, s, self.count, self.partial_count, completed, partial, extreme, self.calibrated)

    def update(self, arr: np.ndarray) -> RepUpdate:
        """Advance with an aspect-corrected landmark frame (33 x 4)."""
        return self.update_angle(combined_angle(arr, self.config, self.min_visibility))


def make_rep_counter(
    exercise: str,
    min_visibility: float = 0.5,
    invisible_frames_before_reset: int = 15,
    calibration: CalibrationSettings | None = None,
) -> RepCounter:
    if exercise not in REP_CONFIGS:
        raise ValueError(f"unsupported exercise: {exercise}")
    return RepCounter(
        REP_CONFIGS[exercise], min_visibility, invisible_frames_before_reset,
        calibration or CalibrationSettings(),
    )  # fmt: skip
