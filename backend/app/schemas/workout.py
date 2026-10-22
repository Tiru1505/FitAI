from datetime import date

from pydantic import BaseModel

from app.schemas.common import ORMModel, UTCDateTime


class ExerciseOut(ORMModel):
    id: int
    slug: str
    name: str
    difficulty: str
    muscle_group: str
    equipment: list[str]
    instructions: list[str]
    form_cues: list[str]
    substitutions: list[str]
    safety_note: str


class PlannedExerciseOut(ORMModel):
    id: int
    day_index: int
    order_index: int
    sets: int
    repetitions: int
    rest_seconds: int
    practice_mode: bool
    notes: str
    exercise: ExerciseOut


class PlanDayOut(BaseModel):
    day_index: int
    weekday: int
    weekday_name: str
    exercises: list[PlannedExerciseOut]


class PlanOut(BaseModel):
    id: int
    goal: str
    template: str
    start_date: date
    status: str
    version: int
    parent_plan_id: int | None
    generated_reason: str
    warnings: list[str]
    days_per_week: int
    schedule: list[int]
    created_at: UTCDateTime
    days: list[PlanDayOut]


class TodayWorkoutOut(BaseModel):
    date: date
    plan_id: int
    is_training_day: bool
    day: PlanDayOut | None
    next_training_date: date | None
    completed_today: bool
