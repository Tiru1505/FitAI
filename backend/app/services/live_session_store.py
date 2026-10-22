"""In-memory store of live-analysis summaries until a session is completed.

Each WebSocket run (e.g. one set) produces a server-computed summary. Summaries for
the same session and exercise are merged here and consumed by
``POST /api/sessions/{id}/complete``. This keeps results server-side rather than
trusting client-reported counts. Being in-memory, pending data is lost if the API
restarts before the session is completed (acceptable for a single-process prototype).
"""

from __future__ import annotations

import threading

_lock = threading.Lock()
_store: dict[int, dict[str, dict]] = {}


def _merge(a: dict, b: dict) -> dict:
    out = {**b, **a}
    for key in ("repetitions", "partial_repetitions", "rep_attempts", "good_reps", "frames", "visible_frames",
                "client_frames_captured", "client_frames_sent", "client_frames_dropped", "sets_recorded"):
        out[key] = a.get(key, 0) + b.get(key, 0)
    errors = dict(a.get("error_counts", {}))
    for code, n in b.get("error_counts", {}).items():
        errors[code] = errors.get(code, 0) + n
    out["error_counts"] = errors
    out["form_score"] = round(out["good_reps"] / out["rep_attempts"], 4) if out["rep_attempts"] else None
    total_frames = out["frames"]
    if total_frames:
        weighted = (a.get("avg_processing_ms") or 0) * a.get("frames", 0) + (b.get("avg_processing_ms") or 0) * b.get("frames", 0)
        out["avg_processing_ms"] = round(weighted / total_frames, 3)
        out["low_visibility_ratio"] = round(1 - out["visible_frames"] / total_frames, 4)
    return out


def add_summary(session_id: int, summary: dict, client_stats: dict | None = None) -> dict:
    record = dict(summary)
    record["sets_recorded"] = 1
    for key in ("frames_captured", "frames_sent", "frames_dropped"):
        record[f"client_{key}"] = int((client_stats or {}).get(key, 0))
    with _lock:
        per_session = _store.setdefault(session_id, {})
        exercise = record["exercise"]
        per_session[exercise] = _merge(per_session[exercise], record) if exercise in per_session else _merge({}, record)
        return per_session[exercise]


def get(session_id: int) -> dict[str, dict]:
    with _lock:
        return dict(_store.get(session_id, {}))


def pop(session_id: int) -> dict[str, dict]:
    with _lock:
        return _store.pop(session_id, {})


def discard(session_ids) -> None:
    with _lock:
        for sid in session_ids:
            _store.pop(sid, None)
