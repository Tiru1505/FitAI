"""Dataset schema, loading and windowing shared by all ML scripts.

Feature construction is imported from the backend (``app.services.pose_service``)
so that training and live inference use exactly the same normalisation.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ML_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = ML_DIR.parent
BACKEND_DIR = REPO_DIR / "backend"
TRAINED_MODELS_DIR = BACKEND_DIR / "trained_models"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services import pose_service as ps  # noqa: E402

META_COLUMNS = [
    "sample_id", "participant_id", "exercise_label", "form_label", "error_label",
    "frame_index", "visibility_score", "image_width", "image_height",
]  # fmt: skip
LANDMARK_COLUMNS = [f"landmark_{i}_{c}" for i in range(ps.NUM_LANDMARKS) for c in ("x", "y", "visibility")]
# z is optional in the CSV; the xyv99 feature set does not use it.
ALL_COLUMNS = META_COLUMNS + LANDMARK_COLUMNS


def read_table(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(path)
    return pd.read_csv(path)


def load_landmark_tables(paths: list[Path]) -> pd.DataFrame:
    frames = [read_table(p) for p in paths]
    df = pd.concat(frames, ignore_index=True)
    missing = [c for c in ALL_COLUMNS if c not in df.columns and c not in ("image_width", "image_height", "error_label")]
    if missing:
        raise ValueError(f"missing columns: {missing[:6]}{'...' if len(missing) > 6 else ''}")
    for col in ("image_width", "image_height"):
        if col not in df.columns:
            df[col] = np.nan
    if "error_label" not in df.columns:
        df["error_label"] = ""
    df["error_label"] = df["error_label"].fillna("")
    df["form_label"] = df["form_label"].fillna("correct")
    df["participant_id"] = df["participant_id"].astype(str)
    df["sample_id"] = df["sample_id"].astype(str)
    return df.sort_values(["sample_id", "frame_index"]).reset_index(drop=True)


def row_to_array(row: pd.Series) -> np.ndarray:
    arr = np.zeros((ps.NUM_LANDMARKS, 4), dtype=np.float32)
    for i in range(ps.NUM_LANDMARKS):
        arr[i, 0] = row[f"landmark_{i}_x"]
        arr[i, 1] = row[f"landmark_{i}_y"]
        arr[i, 2] = row.get(f"landmark_{i}_z", 0.0) or 0.0
        arr[i, 3] = row[f"landmark_{i}_visibility"]
    return arr


def sample_features(sample: pd.DataFrame, min_visibility: float) -> tuple[np.ndarray, np.ndarray]:
    """Return (features [T, 99], low_visibility_flags [T]) for one recorded sample."""
    x = sample[[f"landmark_{i}_x" for i in range(ps.NUM_LANDMARKS)]].to_numpy(np.float32)
    y = sample[[f"landmark_{i}_y" for i in range(ps.NUM_LANDMARKS)]].to_numpy(np.float32)
    v = sample[[f"landmark_{i}_visibility" for i in range(ps.NUM_LANDMARKS)]].to_numpy(np.float32)
    w = sample["image_width"].to_numpy(np.float64)
    h = sample["image_height"].to_numpy(np.float64)
    feats, low = [], []
    core = [ps.IDX[n] for n in ("left_shoulder", "right_shoulder", "left_hip", "right_hip")]
    for t in range(len(sample)):
        arr = np.stack([x[t], y[t], np.zeros_like(x[t]), v[t]], axis=1)
        if np.isfinite(w[t]) and np.isfinite(h[t]) and h[t] > 0:
            arr = ps.aspect_corrected(arr, w[t], h[t])
        feats.append(ps.frame_features(arr))
        low.append(bool(arr[core, 3].min() < min_visibility))
    return np.stack(feats), np.asarray(low)


def windows(n_frames: int, length: int, stride: int) -> list[tuple[int, int]]:
    if n_frames < length:
        return []
    return [(s, s + length) for s in range(0, n_frames - length + 1, stride)]
