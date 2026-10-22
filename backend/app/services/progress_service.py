from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings
from app.models import AdaptationEvent, ExerciseResult, ProgressRecord, WorkoutSession
from app.schemas.progress import AdaptationEventOut, ProgressHistory, ProgressSummary
from app.schemas.session import SessionOut
from app.services import plan_service


def completed_sessions(db: Session, user_id: int, limit: int | None = None) -> list[WorkoutSession]:
    stmt = (
        select(WorkoutSession)
        .where(WorkoutSession.user_id == user_id, WorkoutSession.status == "completed")
        .options(selectinload(WorkoutSession.results).selectinload(ExerciseResult.feedback))
        .order_by(WorkoutSession.completed_at.desc())
    )
    if limit:
        stmt = stmt.limit(limit)
    return list(db.scalars(stmt))


def _avg(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def summary(db: Session, user_id: int, settings: Settings) -> ProgressSummary:
    sessions = completed_sessions(db, user_id)
    plan = plan_service.get_active_plan(db, user_id)
    today = date.today()

    session_series = []
    exercise_series: dict[str, list[dict]] = {}
    error_frequency: dict[str, int] = {}
    for s in reversed(sessions):
        day = plan_service.local_date(s.completed_at).isoformat()
        session_series.append(
            {
                "session_id": s.id,
                "date": day,
                "completion_rate": s.completion_rate,
                "form_score": s.form_score,
                "session_score": s.session_score,
                "repetitions": sum(r.repetitions for r in s.results),
                "duration_seconds": s.duration_seconds,
            }
        )
        for r in s.results:
            exercise_series.setdefault(r.exercise.slug, []).append(
                {"session_id": s.id, "date": day, "repetitions": r.repetitions, "form_score": r.form_score, "completion_rate": r.completion_rate}
            )
            for f in r.feedback:
                error_frequency[f.error_type] = error_frequency.get(f.error_type, 0) + f.occurrences

    latest_feedback: list[str] = []
    if sessions:
        latest = sessions[0]
        latest_feedback = sorted({f.message for r in latest.results for f in r.feedback})
        event = db.scalar(select(AdaptationEvent).where(AdaptationEvent.session_id == latest.id))
        if event:
            latest_feedback += [g for g in event.details.get("guidance", []) if g not in latest_feedback]

    weights = db.scalars(
        select(ProgressRecord)
        .where(ProgressRecord.user_id == user_id, ProgressRecord.weight_kg.is_not(None))
        .order_by(ProgressRecord.date)
    )

    return ProgressSummary(
        sessions_completed=len(sessions),
        total_repetitions=sum(p["repetitions"] for p in session_series),
        average_completion_rate=_avg([s.completion_rate for s in sessions if s.completion_rate is not None]),
        average_form_score=_avg([s.form_score for s in sessions if s.form_score is not None]),
        average_session_score=_avg([s.session_score for s in sessions if s.session_score is not None]),
        consistency_score=plan_service.consistency_score(db, user_id, plan, today, settings.consistency_window_days),
        consistency_window_days=settings.consistency_window_days,
        missed_sessions_last_7_days=plan_service.missed_sessions(db, user_id, plan, today) if plan else 0,
        last_session_at=sessions[0].completed_at if sessions else None,
        latest_feedback=latest_feedback,
        session_series=session_series,
        exercise_series=exercise_series,
        error_frequency=error_frequency,
        weight_series=[{"date": w.date.isoformat(), "weight_kg": w.weight_kg} for w in weights],
    )


def history(db: Session, user_id: int, limit: int) -> ProgressHistory:
    events = db.scalars(
        select(AdaptationEvent).where(AdaptationEvent.user_id == user_id).order_by(AdaptationEvent.created_at.desc()).limit(limit)
    )
    return ProgressHistory(
        sessions=[SessionOut.model_validate(s) for s in completed_sessions(db, user_id, limit)],
        adaptations=[AdaptationEventOut.model_validate(e) for e in events],
    )
