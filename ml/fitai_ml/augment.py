"""Augmentation for pose-landmark windows.

Features are [x, y, visibility] per landmark, hip-centred and body-scale normalised
(see backend/app/services/pose_service.py), so augmentations operate in that normalised space:

  mirror       left/right flip (negate x and swap the paired landmarks) — a squat is still a squat
  time warp    resample the window at 0.8x-1.25x speed — same movement, different tempo
  scale        uniform scale 0.9x-1.1x — body proportions and distance from camera
  rotate       small in-plane rotation (camera tilt)
  jitter       gaussian noise on coordinates — landmark detection noise

These preserve the exercise label. They are the standard defence against a model learning
participant-specific style instead of the movement.
"""

from __future__ import annotations

import numpy as np

from app.services import pose_service as ps

# Index pairs whose names differ only by the left_/right_ prefix.
_PAIRS = [
    (ps.IDX[name], ps.IDX["right_" + name[5:]])
    for name in ps.LANDMARK_NAMES
    if name.startswith("left_") and "right_" + name[5:] in ps.IDX
]


def _as_landmarks(window: np.ndarray) -> np.ndarray:
    """[T, 99] -> [T, 33, 3]"""
    return window.reshape(window.shape[0], ps.NUM_LANDMARKS, 3)


def mirror(window: np.ndarray) -> np.ndarray:
    lm = _as_landmarks(window).copy()
    lm[:, :, 0] *= -1.0
    for left, right in _PAIRS:
        lm[:, [left, right]] = lm[:, [right, left]]
    return lm.reshape(window.shape)


def time_warp(window: np.ndarray, rng: np.random.Generator, low: float = 0.8, high: float = 1.25) -> np.ndarray:
    t = window.shape[0]
    speed = rng.uniform(low, high)
    src = np.clip(np.linspace(0, (t - 1) * speed, t), 0, t - 1)
    lo = np.floor(src).astype(int)
    hi = np.minimum(lo + 1, t - 1)
    frac = (src - lo)[:, None]
    return (window[lo] * (1 - frac) + window[hi] * frac).astype(np.float32)


def scale(window: np.ndarray, rng: np.random.Generator, low: float = 0.9, high: float = 1.1) -> np.ndarray:
    lm = _as_landmarks(window).copy()
    lm[:, :, :2] *= rng.uniform(low, high)
    return lm.reshape(window.shape)


def rotate(window: np.ndarray, rng: np.random.Generator, max_degrees: float = 10.0) -> np.ndarray:
    theta = np.radians(rng.uniform(-max_degrees, max_degrees))
    cos, sin = np.cos(theta), np.sin(theta)
    lm = _as_landmarks(window).copy()
    x, y = lm[:, :, 0].copy(), lm[:, :, 1].copy()
    lm[:, :, 0] = cos * x - sin * y
    lm[:, :, 1] = sin * x + cos * y
    return lm.reshape(window.shape)


def jitter(window: np.ndarray, rng: np.random.Generator, sigma: float = 0.01) -> np.ndarray:
    lm = _as_landmarks(window).copy()
    lm[:, :, :2] += rng.normal(0, sigma, size=lm[:, :, :2].shape)
    return lm.reshape(window.shape)


def augment_window(window: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    out = window
    if rng.random() < 0.5:
        out = mirror(out)
    if rng.random() < 0.8:
        out = time_warp(out, rng)
    if rng.random() < 0.8:
        out = scale(out, rng)
    if rng.random() < 0.5:
        out = rotate(out, rng)
    if rng.random() < 0.8:
        out = jitter(out, rng)
    return out.astype(np.float32)


def augment_dataset(X: np.ndarray, y: np.ndarray, copies: int, seed: int = 42) -> tuple[np.ndarray, np.ndarray]:
    """Return the original data plus `copies` randomly augmented versions of every window."""
    if copies <= 0:
        return X, y
    rng = np.random.default_rng(seed)
    parts_x, parts_y = [X], [y]
    for _ in range(copies):
        parts_x.append(np.stack([augment_window(w, rng) for w in X]))
        parts_y.append(y)
    return np.concatenate(parts_x).astype(np.float32), np.concatenate(parts_y)
