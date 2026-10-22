"""Right-to-delete: removes a user's stored data in foreign-key-safe order."""

from __future__ import annotations

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.models import (
    AdaptationEvent, ExerciseResult, FormFeedback, MealGuidance, PlannedExercise, Profile,
    ProgressRecord, User, WorkoutPlan, WorkoutSession,
)  # fmt: skip
from app.services import live_session_store


def delete_user_data(db: Session, user: User, delete_account: bool) -> dict[str, int]:
    uid = user.id
    session_ids = select(WorkoutSession.id).where(WorkoutSession.user_id == uid)
    result_ids = select(ExerciseResult.id).where(ExerciseResult.session_id.in_(session_ids))
    plan_ids = select(WorkoutPlan.id).where(WorkoutPlan.user_id == uid)
    live_session_store.discard(db.scalars(session_ids).all())

    counts: dict[str, int] = {}

    def run(name: str, stmt) -> None:
        counts[name] = db.execute(stmt).rowcount or 0

    run("form_feedback", delete(FormFeedback).where(FormFeedback.result_id.in_(result_ids)))
    run("exercise_results", delete(ExerciseResult).where(ExerciseResult.session_id.in_(session_ids)))
    run("adaptation_events", delete(AdaptationEvent).where(AdaptationEvent.user_id == uid))
    run("workout_sessions", delete(WorkoutSession).where(WorkoutSession.user_id == uid))
    run("planned_exercises", delete(PlannedExercise).where(PlannedExercise.plan_id.in_(plan_ids)))
    db.execute(update(WorkoutPlan).where(WorkoutPlan.user_id == uid).values(parent_plan_id=None))
    run("workout_plans", delete(WorkoutPlan).where(WorkoutPlan.user_id == uid))
    run("meal_guidance", delete(MealGuidance).where(MealGuidance.user_id == uid))
    run("progress_records", delete(ProgressRecord).where(ProgressRecord.user_id == uid))
    run("profiles", delete(Profile).where(Profile.user_id == uid))
    if delete_account:
        run("users", delete(User).where(User.id == uid))
    db.commit()
    db.expunge_all()
    return counts
