"""Pose-landmark utilities shared by live inference, the REST analyzer and the ML pipeline.

Landmarks follow the MediaPipe Pose Landmarker convention: 33 points with x and y
normalised to the image width and height (y grows downward), z relative depth,
and a visibility score. The ML training scripts import this module so that
training and serving use exactly the same feature construction.
"""

from __future__ import annotations

import numpy as np

LANDMARK_NAMES = [
    "nose", "left_eye_inner", "left_eye", "left_eye_outer", "right_eye_inner", "right_eye",
    "right_eye_outer", "left_ear", "right_ear", "mouth_left", "mouth_right", "left_shoulder",
    "right_shoulder", "left_elbow", "right_elbow", "left_wrist", "right_wrist", "left_pinky",
    "right_pinky", "left_index", "right_index", "left_thumb", "right_thumb", "left_hip",
    "right_hip", "left_knee", "right_knee", "left_ankle", "right_ankle", "left_heel",
    "right_heel", "left_foot_index", "right_foot_index",
]  # fmt: skip
NUM_LANDMARKS = len(LANDMARK_NAMES)
IDX = {name: i for i, name in enumerate(LANDMARK_NAMES)}

X, Y, Z, VIS = 0, 1, 2, 3
FEATURE_SET = "xyv99"
FEATURES_PER_FRAME = NUM_LANDMARKS * 3


def to_array(landmarks) -> np.ndarray:
    """Convert a 33 x 4 nested list ([x, y, z, visibility]) into a float array."""
    arr = np.asarray(landmarks, dtype=np.float32)
    if arr.shape != (NUM_LANDMARKS, 4):
        raise ValueError(f"expected landmarks shape (33, 4), got {arr.shape}")
    if not np.all(np.isfinite(arr)):
        raise ValueError("landmarks contain non-finite values")
    return arr


def aspect_corrected(arr: np.ndarray, image_width: float | None, image_height: float | None) -> np.ndarray:
    """Scale x so that x and y share the same unit; needed for correct angles on non-square frames."""
    out = arr.copy()
    if image_width and image_height:
        out[:, X] *= image_width / image_height
    return out


def point(arr: np.ndarray, name: str) -> np.ndarray:
    return arr[IDX[name], :2]


def visibility(arr: np.ndarray, names) -> float:
    return float(min(arr[IDX[n], VIS] for n in names))


def midpoint(arr: np.ndarray, a: str, b: str) -> np.ndarray:
    return (point(arr, a) + point(arr, b)) / 2.0


def joint_angle(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
    """Angle ABC in degrees (0-180) using 2D coordinates."""
    ba, bc = a - b, c - b
    denom = float(np.linalg.norm(ba) * np.linalg.norm(bc))
    if denom < 1e-9:
        return float("nan")
    cosine = float(np.clip(np.dot(ba, bc) / denom, -1.0, 1.0))
    return float(np.degrees(np.arccos(cosine)))


def side_angle(arr: np.ndarray, side: str, joints: tuple[str, str, str]) -> tuple[float, float]:
    """Return (angle, visibility) for e.g. side='left', joints=('hip', 'knee', 'ankle')."""
    names = [f"{side}_{j}" for j in joints]
    return joint_angle(*(point(arr, n) for n in names)), visibility(arr, names)


def angle_from_vertical(lower: np.ndarray, upper: np.ndarray) -> float:
    """Angle in degrees between the vector lower->upper and straight up (image y decreases upward)."""
    v = upper - lower
    norm = float(np.linalg.norm(v))
    if norm < 1e-9:
        return float("nan")
    cosine = float(np.clip(-v[1] / norm, -1.0, 1.0))
    return float(np.degrees(np.arccos(cosine)))


def torso_angle(arr: np.ndarray) -> float:
    return angle_from_vertical(midpoint(arr, "left_hip", "right_hip"), midpoint(arr, "left_shoulder", "right_shoulder"))


def body_scale(arr: np.ndarray) -> float:
    torso = float(np.linalg.norm(midpoint(arr, "left_shoulder", "right_shoulder") - midpoint(arr, "left_hip", "right_hip")))
    shoulders = float(np.linalg.norm(point(arr, "left_shoulder") - point(arr, "right_shoulder")))
    return max(torso, shoulders, 1e-6)


def normalize_frame(arr: np.ndarray) -> np.ndarray:
    """Center on the hip midpoint and divide by body scale (x, y only)."""
    out = arr.copy()
    center = midpoint(arr, "left_hip", "right_hip")
    scale = body_scale(arr)
    out[:, X] = (arr[:, X] - center[0]) / scale
    out[:, Y] = (arr[:, Y] - center[1]) / scale
    return out


def frame_features(arr: np.ndarray) -> np.ndarray:
    """99-dim feature vector: normalised x, y and raw visibility for each landmark."""
    norm = normalize_frame(arr)
    return norm[:, [X, Y, VIS]].reshape(-1).astype(np.float32)


def sequence_features(frames: list[np.ndarray]) -> np.ndarray:
    return np.stack([frame_features(f) for f in frames]).astype(np.float32)
