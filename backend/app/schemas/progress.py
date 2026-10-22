from datetime import date

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel, UTCDateTime
from app.schemas.session import SessionOut


class ProgressSummary(BaseModel):
    sessions_completed: int
    total_repetitions: int
    average_completion_rate: float | None
    average_form_score: float | None
    average_session_score: float | None
    consistency_score: float
    consistency_window_days: int
    missed_sessions_last_7_days: int
    last_session_at: UTCDateTime | None
    latest_feedback: list[str]
    session_series: list[dict]
    exercise_series: dict[str, list[dict]]
    error_frequency: dict[str, int]
    weight_series: list[dict]


class AdaptationEventOut(ORMModel):
    id: int
    session_id: int | None
    old_plan_id: int | None
    new_plan_id: int | None
    reason: str
    details: dict
    created_at: UTCDateTime


class ProgressHistory(BaseModel):
    sessions: list[SessionOut]
    adaptations: list[AdaptationEventOut]


class ProgressRecordIn(BaseModel):
    date: date
    weight_kg: float | None = Field(default=None, ge=30, le=300)
    notes: str = Field(default="", max_length=500)


class ProgressRecordOut(ORMModel):
    id: int
    date: date
    weight_kg: float | None
    notes: str
    consistency_score: float | None
