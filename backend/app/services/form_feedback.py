"""Rule-based form analysis with interpretable geometric checks.

These rules are the transparent baseline. When a trained form classifier is
available its confident predictions are merged in by ``live_analyzer``. All
checks are 2D heuristics: some only apply to a front view (e.g. knees caving)
or a side view (e.g. hip sag), and each check gates itself on the view it needs.
Thresholds are starting points to be tuned against labelled recordings.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from app.services import pose_service as ps
from app.services.rep_counter import RepUpdate


@dataclass(frozen=True)
class FormError:
    code: str
    message: str
    severity: str  # "minor" | "major"


FORM_ERRORS: dict[str, FormError] = {
    e.code: e
    for e in [
        FormError("insufficient_range", "Use a fuller range of motion that you can control.", "minor"),
        FormError("knees_caving", "Keep your knees aligned with your toes.", "major"),
        FormError("forward_lean", "Keep your chest up and avoid leaning too far forward.", "minor"),
        FormError("torso_lean", "Keep your torso upright and your core braced.", "minor"),
        FormError("hip_sag", "Keep your hips in line with your shoulders and ankles.", "major"),
        FormError("hip_pike", "Lower your hips so your body forms a straight line.", "minor"),
        FormError("elbow_drift", "Keep your elbows close to your sides.", "minor"),
        FormError("torso_swing", "Avoid swinging your body; control the weight.", "minor"),
        FormError("uneven_arms", "Press both arms up evenly.", "minor"),
    ]
}

PARTIAL_MESSAGES = {
    "squat": "Lower a little further, to a depth you can control.",
    "lunge": "Bend both knees a little more if it feels comfortable.",
    "push_up": "Lower your chest a bit further, or try an incline variation.",
    "biceps_curl": "Curl through a fuller range of motion.",
    "shoulder_press": "Press until your arms are nearly straight overhead.",
}

PHASE_CUES = {
    "not_started": "Get into the start position with your whole body in view.",
    "start": "Ready. Begin the movement with control.",
    "descending": "Controlled movement.",
    "bottom": "Good depth. Now return with control.",
    "ascending": "Keep going.",
    "complete": "Good rep.",
}

MOVING_PHASES = ("descending", "bottom", "ascending")


def message_for(code: str) -> str:
    error = FORM_ERRORS.get(code)
    return error.message if error else f"Form issue detected: {code.replace('_', ' ')}."


@dataclass
class FrameForm:
    status: str  # not_started | good | minor_error | major_error | uncertain
    active_errors: list[str]
    feedback: str


def _vis_ok(arr: np.ndarray, names, min_vis: float) -> bool:
    return ps.visibility(arr, names) >= min_vis


def _check_squat(arr, phase, min_vis, _ctx) -> set[str]:
    errors = set()
    if phase not in MOVING_PHASES:
        return errors
    legs = ["left_knee", "right_knee", "left_ankle", "right_ankle", "left_shoulder", "right_shoulder"]
    if _vis_ok(arr, legs, min_vis) and phase == "bottom":
        scale = ps.body_scale(arr)
        shoulder_w = abs(ps.point(arr, "left_shoulder")[0] - ps.point(arr, "right_shoulder")[0])
        knee_w = abs(ps.point(arr, "left_knee")[0] - ps.point(arr, "right_knee")[0])
        ankle_w = abs(ps.point(arr, "left_ankle")[0] - ps.point(arr, "right_ankle")[0])
        front_view = shoulder_w > 0.5 * scale
        if front_view and ankle_w > 0.3 * scale and knee_w < 0.75 * ankle_w:
            errors.add("knees_caving")
    if _vis_ok(arr, ["left_hip", "right_hip", "left_shoulder", "right_shoulder"], min_vis):
        if ps.torso_angle(arr) > 60:
            errors.add("forward_lean")
    return errors


def _check_lunge(arr, phase, min_vis, _ctx) -> set[str]:
    if phase in MOVING_PHASES and _vis_ok(arr, ["left_hip", "right_hip", "left_shoulder", "right_shoulder"], min_vis):
        if ps.torso_angle(arr) > 30:
            return {"torso_lean"}
    return set()


def _check_push_up(arr, phase, min_vis, _ctx) -> set[str]:
    if phase == "not_started":
        return set()
    best = None
    for side in ("left", "right"):
        names = [f"{side}_shoulder", f"{side}_hip", f"{side}_ankle"]
        vis = ps.visibility(arr, names)
        if vis >= min_vis and (best is None or vis > best[1]):
            best = (side, vis)
    if best is None:
        return set()
    side = best[0]
    s, h, a = (ps.point(arr, f"{side}_{j}") for j in ("shoulder", "hip", "ankle"))
    dx, dy = a[0] - s[0], a[1] - s[1]
    if abs(dx) <= abs(dy):  # body not roughly horizontal: not a side view of a push-up
        return set()
    if ps.joint_angle(s, h, a) >= 160:
        return set()
    line_y = s[1] + (h[0] - s[0]) * dy / dx
    return {"hip_sag"} if h[1] > line_y else {"hip_pike"}


def _check_biceps_curl(arr, phase, min_vis, ctx) -> set[str]:
    errors = set()
    if phase not in MOVING_PHASES:
        return errors
    for side in ("left", "right"):
        names = [f"{side}_shoulder", f"{side}_elbow", f"{side}_wrist"]
        if _vis_ok(arr, names, min_vis):
            upper_arm = ps.angle_from_vertical(ps.point(arr, f"{side}_elbow"), ps.point(arr, f"{side}_shoulder"))
            if upper_arm > 35:
                errors.add("elbow_drift")
    torso = ctx.get("torso_range")
    if torso and torso[1] - torso[0] > 15:
        errors.add("torso_swing")
    return errors


def _check_shoulder_press(arr, phase, min_vis, _ctx) -> set[str]:
    errors = set()
    if phase not in MOVING_PHASES:
        return errors
    if _vis_ok(arr, ["left_hip", "right_hip", "left_shoulder", "right_shoulder"], min_vis) and ps.torso_angle(arr) > 20:
        errors.add("torso_lean")
    left, lv = ps.side_angle(arr, "left", ("shoulder", "elbow", "wrist"))
    right, rv = ps.side_angle(arr, "right", ("shoulder", "elbow", "wrist"))
    if lv >= min_vis and rv >= min_vis and abs(left - right) > 35:
        errors.add("uneven_arms")
    return errors


CHECKS = {
    "squat": _check_squat,
    "lunge": _check_lunge,
    "push_up": _check_push_up,
    "biceps_curl": _check_biceps_curl,
    "shoulder_press": _check_shoulder_press,
}


@dataclass
class FormAnalyzer:
    exercise: str
    min_visibility: float = 0.5
    persist_frames: int = 5
    message_hold_frames: int = 20

    rep_log: list[set[str]] = field(default_factory=list)
    _streaks: dict[str, int] = field(default_factory=dict)
    _current_rep_errors: set[str] = field(default_factory=set)
    _torso_range: list[float] | None = None
    _held_message: str | None = None
    _held_frames: int = 0

    def update(self, arr: np.ndarray | None, rep: RepUpdate) -> FrameForm:
        if arr is None or not rep.visible:
            self._streaks.clear()
            return FrameForm("uncertain", [], "Move so your whole body is clearly visible to the camera.")

        if rep.phase in MOVING_PHASES and _vis_ok(arr, ["left_hip", "right_hip", "left_shoulder", "right_shoulder"], self.min_visibility):
            t = ps.torso_angle(arr)
            if np.isfinite(t):
                self._torso_range = [t, t] if self._torso_range is None else [min(self._torso_range[0], t), max(self._torso_range[1], t)]

        violated = CHECKS[self.exercise](arr, rep.phase, self.min_visibility, {"torso_range": self._torso_range})
        for code in list(self._streaks):
            if code not in violated:
                del self._streaks[code]
        active = []
        for code in violated:
            self._streaks[code] = self._streaks.get(code, 0) + 1
            if self._streaks[code] >= self.persist_frames:
                active.append(code)
                self._current_rep_errors.add(code)

        if rep.partial_rep:
            self.rep_log.append(self._current_rep_errors | {"insufficient_range"})
            self._end_rep(PARTIAL_MESSAGES[self.exercise])
        elif rep.rep_completed:
            errors = set(self._current_rep_errors)
            self.rep_log.append(errors)
            self._end_rep(message_for(sorted(errors)[0]) if errors else "Good rep.")

        return FrameForm(self._status(active, rep.phase), sorted(active), self._feedback(active, rep.phase))

    def _end_rep(self, message: str) -> None:
        self._current_rep_errors = set()
        self._torso_range = None
        self._held_message, self._held_frames = message, self.message_hold_frames

    def _status(self, active: list[str], phase: str) -> str:
        if any(FORM_ERRORS[c].severity == "major" for c in active if c in FORM_ERRORS):
            return "major_error"
        if active:
            return "minor_error"
        return "not_started" if phase == "not_started" else "good"

    def _feedback(self, active: list[str], phase: str) -> str:
        if active:
            major = [c for c in active if FORM_ERRORS.get(c) and FORM_ERRORS[c].severity == "major"]
            return message_for((major or active)[0])
        if self._held_frames > 0 and self._held_message:
            self._held_frames -= 1
            return self._held_message
        return PHASE_CUES.get(phase, "")

    def summary(self) -> dict:
        counts: dict[str, int] = {}
        for errors in self.rep_log:
            for code in errors:
                counts[code] = counts.get(code, 0) + 1
        attempts = len(self.rep_log)
        good = sum(1 for errors in self.rep_log if not errors)
        return {
            "rep_attempts": attempts,
            "good_reps": good,
            "form_score": round(good / attempts, 4) if attempts else None,
            "error_counts": counts,
        }
