"""Builds synthetic 33-point landmark frames with controlled joint angles for tests."""

import math

from app.services.pose_service import IDX, NUM_LANDMARKS


def blank(visibility: float = 0.99) -> list[list[float]]:
    return [[0.5, 0.5, 0.0, visibility] for _ in range(NUM_LANDMARKS)]


def _set(frame, name, x, y):
    frame[IDX[name]][0] = x
    frame[IDX[name]][1] = y


def squat_side_view(knee_angle_deg: float, torso_lean_deg: float = 10.0) -> list[list[float]]:
    """Side view: ankle fixed, shin vertical, thigh rotated so hip-knee-ankle equals knee_angle_deg."""
    f = blank()
    seg = 0.2
    ankle = (0.5, 0.9)
    knee = (0.5, ankle[1] - seg)
    theta = math.radians(knee_angle_deg)
    # Shin points down from knee (0, +1); thigh direction is the shin rotated by theta.
    hip = (knee[0] - seg * math.sin(theta), knee[1] + seg * math.cos(theta))
    lean = math.radians(torso_lean_deg)
    shoulder = (hip[0] + 0.25 * math.sin(lean), hip[1] - 0.25 * math.cos(lean))
    for side in ("left", "right"):
        _set(f, f"{side}_ankle", *ankle)
        _set(f, f"{side}_knee", *knee)
        _set(f, f"{side}_hip", *hip)
        _set(f, f"{side}_shoulder", *shoulder)
        _set(f, f"{side}_elbow", shoulder[0], shoulder[1] + 0.12)
        _set(f, f"{side}_wrist", shoulder[0], shoulder[1] + 0.24)
    return f


def curl_front_view(elbow_angle_deg: float, elbow_drift_deg: float = 0.0) -> list[list[float]]:
    f = blank()
    for side, dx in (("left", 0.1), ("right", -0.1)):
        shoulder = (0.5 + dx, 0.3)
        drift = math.radians(elbow_drift_deg)
        elbow = (shoulder[0] + 0.15 * math.sin(drift), shoulder[1] + 0.15 * math.cos(drift))
        theta = math.radians(180 - elbow_angle_deg)
        # Forearm rotates from pointing down, in the image plane.
        wrist = (elbow[0] + 0.15 * math.sin(theta + drift), elbow[1] + 0.15 * math.cos(theta + drift))
        _set(f, f"{side}_shoulder", *shoulder)
        _set(f, f"{side}_elbow", *elbow)
        _set(f, f"{side}_wrist", *wrist)
        _set(f, f"{side}_hip", 0.5 + dx * 0.8, 0.6)
        _set(f, f"{side}_knee", 0.5 + dx * 0.8, 0.75)
        _set(f, f"{side}_ankle", 0.5 + dx * 0.8, 0.9)
    return f


def angle_path(start: float, end: float, steps: int) -> list[float]:
    return [start + (end - start) * i / (steps - 1) for i in range(steps)]


def rep_angles(high: float, low: float, reps: int, steps: int = 20, hold: int = 6) -> list[float]:
    seq = [high] * hold
    for _ in range(reps):
        seq += angle_path(high, low, steps) + [low] * 3 + angle_path(low, high, steps) + [high] * hold
    return seq
