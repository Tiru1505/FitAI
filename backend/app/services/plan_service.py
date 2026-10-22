"""Database glue between the pure recommender/coach logic and the ORM models."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Exercise, PlannedExercise, Profile, WorkoutPlan, WorkoutSession
from app.schemas.workout import PlanDayOut, PlannedExerciseOut, PlanOut
from app.services.recommender_service import (
    WEEKDAYS, ExerciseInfo, PlanDraft, Prescription, ProfileInput, generate_plan,
)  # fmt: skip


def profile_input(profile: Profile) -> ProfileInput:
    return ProfileInput(
        goal=profile.goal,
        experience=profile.experience,
        equipment=list(profile.equipment or []),
        days_per_week=profile.days_per_week,
        session_minutes=profile.session_minutes,
        exclusions=list(profile.exclusions or []),
        preferred_days=list(profile.preferred_days or []),
        health_flags=list(profile.health_flags or []),
    )


def exercise_map(db: Session) -> dict[str, Exercise]:
    return {e.slug: e for e in db.scalars(select(Exercise))}


def get_active_plan(db: Session, user_id: int) -> WorkoutPlan | None:
    return db.scalar(
        select(WorkoutPlan)
        .where(WorkoutPlan.user_id == user_id, WorkoutPlan.status == "active")
        .order_by(WorkoutPlan.created_at.desc(), WorkoutPlan.id.desc())
    )


def save_plan(
    db: Session, user_id: int, draft: PlanDraft, *, start_date: date,
    parent: WorkoutPlan | None = None, reason_prefix: str = "",
) -> WorkoutPlan:  # fmt: skip
    exercises = exercise_map(db)
    for old in db.scalars(select(WorkoutPlan).where(WorkoutPlan.user_id == user_id, WorkoutPlan.status == "active")):
        old.status = "superseded"
    plan = WorkoutPlan(
        user_id=user_id,
        goal=draft.goal,
        template=draft.template,
        start_date=start_date,
        status="active",
        generated_reason=(reason_prefix + "\n".join(draft.reasons)).strip(),
        warnings=draft.warnings,
        days_per_week=len(draft.schedule),
        schedule=draft.schedule,
        version=(parent.version + 1) if parent else 1,
        parent_plan_id=parent.id if parent else None,
    )
    for rx in draft.prescriptions:
        plan.exercises.append(
            PlannedExercise(
                exercise_id=exercises[rx.exercise_slug].id,
                day_index=rx.day_index,
                sets=rx.sets,
                repetitions=rx.repetitions,
                rest_seconds=rx.rest_seconds,
                order_index=rx.order_index,
                practice_mode=rx.practice_mode,
                notes=rx.notes,
            )
        )
    db.add(plan)
    db.flush()
    return plan


def generate_for_profile(db: Session, profile: Profile) -> WorkoutPlan:
    catalog = [ExerciseInfo(e.slug, e.name, list(e.equipment)) for e in exercise_map(db).values()]
    draft = generate_plan(profile_input(profile), catalog)
    return save_plan(db, profile.user_id, draft, start_date=date.today())


def prescriptions_of(plan: WorkoutPlan) -> list[Prescription]:
    return [
        Prescription(pe.exercise.slug, pe.day_index, pe.order_index, pe.sets, pe.repetitions, pe.rest_seconds, pe.notes, pe.practice_mode)
        for pe in plan.exercises
    ]


def day_index_for(plan: WorkoutPlan, on: date) -> int | None:
    weekday = on.weekday()
    return plan.schedule.index(weekday) if weekday in plan.schedule else None


def next_training_date(plan: WorkoutPlan, after: date) -> date | None:
    for offset in range(1, 8):
        d = after + timedelta(days=offset)
        if d.weekday() in plan.schedule:
            return d
    return None


def planned_dates(plan: WorkoutPlan, start: date, end: date) -> list[date]:
    """Scheduled training dates in [start, end], not before the plan started."""
    start = max(start, plan.start_date)
    days = []
    d = start
    while d <= end:
        if d.weekday() in plan.schedule:
            days.append(d)
        d += timedelta(days=1)
    return days


def local_date(dt: datetime) -> date:
    """Timestamps are stored in UTC; training days are judged in the server's local time zone."""
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone().date()


def completed_session_dates(db: Session, user_id: int, start: date, end: date) -> set[date]:
    start_dt = datetime.combine(start, datetime.min.time()).astimezone(timezone.utc)
    end_dt = datetime.combine(end + timedelta(days=1), datetime.min.time()).astimezone(timezone.utc)
    rows = db.scalars(
        select(WorkoutSession.completed_at).where(
            WorkoutSession.user_id == user_id,
            WorkoutSession.status == "completed",
            WorkoutSession.completed_at >= start_dt,
            WorkoutSession.completed_at < end_dt,
        )
    )
    return {local_date(r) for r in rows if r is not None}


def missed_sessions(db: Session, user_id: int, plan: WorkoutPlan, today: date, days: int = 7) -> int:
    start, end = today - timedelta(days=days), today - timedelta(days=1)
    done = completed_session_dates(db, user_id, start, end)
    return sum(1 for d in planned_dates(plan, start, end) if d not in done)


def consistency_score(db: Session, user_id: int, plan: WorkoutPlan | None, today: date, window_days: int) -> float:
    """Share of scheduled training days in the window with a completed session (1.0 when nothing was scheduled yet)."""
    if plan is None:
        return 1.0
    start = today - timedelta(days=window_days - 1)
    scheduled = planned_dates(plan, start, today)
    done = completed_session_dates(db, user_id, start, today)
    if not scheduled:
        return 1.0
    return round(min(1.0, len(done) / len(scheduled)), 4)


def plan_out(plan: WorkoutPlan) -> PlanOut:
    days = []
    for day_index, weekday in enumerate(plan.schedule):
        items = [pe for pe in plan.exercises if pe.day_index == day_index]
        days.append(
            PlanDayOut(
                day_index=day_index,
                weekday=weekday,
                weekday_name=WEEKDAYS[weekday],
                exercises=[PlannedExerciseOut.model_validate(pe) for pe in sorted(items, key=lambda p: p.order_index)],
            )
        )
    return PlanOut(
        id=plan.id, goal=plan.goal, template=plan.template, start_date=plan.start_date, status=plan.status,
        version=plan.version, parent_plan_id=plan.parent_plan_id, generated_reason=plan.generated_reason,
        warnings=plan.warnings or [], days_per_week=plan.days_per_week, schedule=plan.schedule,
        created_at=plan.created_at, days=days,
    )  # fmt: skip
