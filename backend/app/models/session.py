from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.exercise import Exercise
from app.models.user import utcnow


class WorkoutSession(Base):
    __tablename__ = "workout_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("workout_plans.id", ondelete="SET NULL"))
    day_index: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="in_progress")  # in_progress | completed
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    completion_rate: Mapped[float | None] = mapped_column(Float)
    form_score: Mapped[float | None] = mapped_column(Float)
    session_score: Mapped[float | None] = mapped_column(Float)
    perceived_difficulty: Mapped[int | None] = mapped_column(Integer)
    ended_early: Mapped[bool] = mapped_column(default=False)
    score_breakdown: Mapped[dict] = mapped_column(JSON, default=dict)
    inference_stats: Mapped[dict] = mapped_column(JSON, default=dict)

    results: Mapped[list["ExerciseResult"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class ExerciseResult(Base):
    __tablename__ = "exercise_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("workout_sessions.id", ondelete="CASCADE"), index=True)
    exercise_id: Mapped[int] = mapped_column(ForeignKey("exercises.id"))
    planned_sets: Mapped[int] = mapped_column(Integer, default=0)
    planned_repetitions: Mapped[int] = mapped_column(Integer, default=0)
    repetitions: Mapped[int] = mapped_column(Integer, default=0)
    partial_repetitions: Mapped[int] = mapped_column(Integer, default=0)
    completion_rate: Mapped[float] = mapped_column(Float, default=0.0)
    form_score: Mapped[float | None] = mapped_column(Float)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    difficulty_rating: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(16), default="live")  # live | manual | none

    session: Mapped[WorkoutSession] = relationship(back_populates="results")
    exercise: Mapped[Exercise] = relationship(lazy="joined")
    feedback: Mapped[list["FormFeedback"]] = relationship(
        back_populates="result", cascade="all, delete-orphan"
    )

    @property
    def exercise_slug(self) -> str:
        return self.exercise.slug

    @property
    def exercise_name(self) -> str:
        return self.exercise.name


class FormFeedback(Base):
    __tablename__ = "form_feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    result_id: Mapped[int] = mapped_column(ForeignKey("exercise_results.id", ondelete="CASCADE"), index=True)
    error_type: Mapped[str] = mapped_column(String(40))
    message: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float)
    occurrences: Mapped[int] = mapped_column(Integer, default=1)
    source: Mapped[str] = mapped_column(String(16), default="rules")  # rules | model

    result: Mapped[ExerciseResult] = relationship(back_populates="feedback")
