from pydantic import BaseModel, Field, model_validator

from app.schemas.common import ExerciseSlug, ORMModel, UTCDateTime


class SessionStartRequest(BaseModel):
    plan_id: int | None = None
    day_index: int | None = Field(default=None, ge=0, le=6)


class FormFeedbackOut(ORMModel):
    error_type: str
    message: str
    confidence: float | None
    occurrences: int
    source: str


class ExerciseResultOut(ORMModel):
    id: int
    exercise_id: int
    planned_sets: int
    planned_repetitions: int
    repetitions: int
    partial_repetitions: int
    completion_rate: float
    form_score: float | None
    error_count: int
    difficulty_rating: int | None
    source: str
    feedback: list[FormFeedbackOut]
    exercise_slug: str
    exercise_name: str


class SessionOut(ORMModel):
    id: int
    plan_id: int | None
    day_index: int | None
    status: str
    started_at: UTCDateTime
    completed_at: UTCDateTime | None
    duration_seconds: int | None
    completion_rate: float | None
    form_score: float | None
    session_score: float | None
    perceived_difficulty: int | None
    ended_early: bool
    score_breakdown: dict
    inference_stats: dict
    results: list[ExerciseResultOut]


class ExerciseCompletionIn(BaseModel):
    exercise_slug: ExerciseSlug
    difficulty_rating: int | None = Field(default=None, ge=1, le=5)
    # Only used when no live (camera) data was recorded for this exercise.
    manual_repetitions: int | None = Field(default=None, ge=0, le=1000)


class SessionCompleteRequest(BaseModel):
    perceived_difficulty: int = Field(ge=1, le=5)
    ended_early: bool = False
    exercises: list[ExerciseCompletionIn] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def unique_exercises(self):
        slugs = [e.exercise_slug for e in self.exercises]
        if len(slugs) != len(set(slugs)):
            raise ValueError("each exercise may appear only once")
        return self


class AdaptationDecisionOut(BaseModel):
    exercise_slug: str | None
    action: str
    reason: str
    changes: dict


class SessionCompleteResponse(BaseModel):
    session: SessionOut
    adaptation_applied: bool
    new_plan_id: int | None
    decisions: list[AdaptationDecisionOut]
    guidance: list[str]


class LiveResultsOut(BaseModel):
    session_id: int
    exercises: dict[str, dict]
