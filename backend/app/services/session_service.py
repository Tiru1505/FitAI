"""Completing a workout session: store results, score it, and run adaptive coaching."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import AdaptationEvent, ExerciseResult, FormFeedback, ProgressRecord, User, WorkoutPlan, WorkoutSession
from app.schemas.session import AdaptationDecisionOut, SessionCompleteRequest, SessionCompleteResponse, SessionOut
from app.services import live_session_store, plan_service
from app.services.adaptive_coach import CoachConfig, ExercisePerformance, compute_session_score, decide_adaptations
from app.services.form_feedback import message_for
from app.services.recommender_service import PlanDraft


def _recent_error_sets(db: Session, user_id: int, exercise_id: int, limit: int) -> list[set[str]]:
    results = db.scalars(
        select(ExerciseResult)
        .join(WorkoutSession, ExerciseResult.session_id == WorkoutSession.id)
        .where(
            WorkoutSession.user_id == user_id,
            WorkoutSession.status == "completed",
            ExerciseResult.exercise_id == exercise_id,
            ExerciseResult.source == "live",
        )
        .order_by(WorkoutSession.completed_at.desc(), ExerciseResult.id.desc())
        .limit(limit)
    )
    return [{f.error_type for f in r.feedback} for r in results]


def _recently_shortened(db: Session, user_id: int, now: datetime) -> bool:
    events = db.scalars(
        select(AdaptationEvent).where(
            AdaptationEvent.user_id == user_id, AdaptationEvent.created_at >= now - timedelta(days=7)
        )
    )
    return any("shorten" in (e.details or {}).get("actions", []) for e in events)


def _inference_stats(live: dict[str, dict]) -> dict:
    if not live:
        return {}
    frames = sum(s.get("frames", 0) for s in live.values())
    weighted_ms = sum((s.get("avg_processing_ms") or 0) * s.get("frames", 0) for s in live.values())
    captured = sum(s.get("client_frames_captured", 0) for s in live.values())
    dropped = sum(s.get("client_frames_dropped", 0) for s in live.values())
    visible = sum(s.get("visible_frames", 0) for s in live.values())
    return {
        "frames_analyzed": frames,
        "avg_server_processing_ms": round(weighted_ms / frames, 3) if frames else None,
        "low_visibility_ratio": round(1 - visible / frames, 4) if frames else None,
        "client_frames_captured": captured,
        "client_frames_dropped": dropped,
        "client_dropped_frame_ratio": round(dropped / captured, 4) if captured else None,
    }


def complete_session(
    db: Session, user: User, ws: WorkoutSession, req: SessionCompleteRequest, settings: Settings
) -> SessionCompleteResponse:
    now = datetime.now(timezone.utc)
    today = date.today()
    plan = db.get(WorkoutPlan, ws.plan_id) if ws.plan_id else None
    exercises = plan_service.exercise_map(db)
    live = live_session_store.pop(ws.id)
    manual = {e.exercise_slug: e for e in req.exercises}

    planned = [pe for pe in plan.exercises if pe.day_index == ws.day_index] if plan and ws.day_index is not None else []
    targets = {pe.exercise.slug: (pe.sets, pe.repetitions) for pe in planned}
    slugs = list(targets) + [s for s in list(live) + list(manual) if s not in targets]
    slugs = list(dict.fromkeys(slugs))

    results: list[ExerciseResult] = []
    for slug in slugs:
        sets, reps = targets.get(slug, (0, 0))
        target_total = sets * reps
        summary, man = live.get(slug), manual.get(slug)
        error_counts: dict[str, int] = {}
        if summary:
            done, partial, form_score, source = summary["repetitions"], summary["partial_repetitions"], summary["form_score"], "live"
            error_counts = summary.get("error_counts", {})
        elif man and man.manual_repetitions is not None:
            done, partial, form_score, source = man.manual_repetitions, 0, None, "manual"
        else:
            done, partial, form_score, source = 0, 0, None, "none"
        completion = min(1.0, done / target_total) if target_total else (1.0 if done > 0 else 0.0)
        result = ExerciseResult(
            exercise_id=exercises[slug].id,
            planned_sets=sets,
            planned_repetitions=reps,
            repetitions=done,
            partial_repetitions=partial,
            completion_rate=round(completion, 4),
            form_score=form_score,
            error_count=sum(error_counts.values()),
            difficulty_rating=man.difficulty_rating if man else None,
            source=source,
        )
        for code, n in sorted(error_counts.items()):
            is_model = code.startswith("model:")
            clean = code.removeprefix("model:")
            result.feedback.append(
                FormFeedback(error_type=clean, message=message_for(clean), occurrences=n, source="model" if is_model else "rules")
            )
        ws.results.append(result)
        results.append(result)

    scored = [r for r in results if r.planned_sets] or results
    completion_rate = sum(r.completion_rate for r in scored) / len(scored) if scored else 0.0
    # Session form score: live form scores weighted by the number of evaluated rep attempts.
    attempts = [(live[s]["rep_attempts"], live[s]["form_score"]) for s in slugs if s in live and live[s].get("form_score") is not None]
    total_attempts = sum(a for a, _ in attempts)
    form_score = sum(a * f for a, f in attempts) / total_attempts if total_attempts else None

    ws.status = "completed"
    ws.completed_at = now
    started = ws.started_at if ws.started_at.tzinfo else ws.started_at.replace(tzinfo=timezone.utc)
    ws.duration_seconds = max(0, int((now - started).total_seconds()))
    ws.perceived_difficulty = req.perceived_difficulty
    ws.ended_early = req.ended_early
    ws.completion_rate = round(completion_rate, 4)
    ws.form_score = round(form_score, 4) if form_score is not None else None
    ws.inference_stats = _inference_stats(live)
    db.flush()

    config = CoachConfig.from_settings(settings)
    consistency = plan_service.consistency_score(db, user.id, plan, today, settings.consistency_window_days)
    breakdown = compute_session_score(completion_rate, form_score, consistency, req.perceived_difficulty, config)
    ws.session_score = breakdown.session_score
    ws.score_breakdown = asdict(breakdown)

    record = db.scalar(select(ProgressRecord).where(ProgressRecord.user_id == user.id, ProgressRecord.date == today))
    if record is None:
        record = ProgressRecord(user_id=user.id, date=today)
        db.add(record)
    record.consistency_score = consistency

    decisions_out: list[AdaptationDecisionOut] = []
    guidance: list[str] = []
    new_plan_id = None
    applied = False
    if plan is not None and plan.status == "active" and ws.day_index is not None:
        performances = []
        for slug, r in zip(slugs, results):
            if not r.planned_sets:
                continue
            man = manual.get(slug)
            performances.append(
                ExercisePerformance(
                    exercise_slug=slug,
                    completion_rate=r.completion_rate,
                    form_score=r.form_score,
                    difficulty_rating=(man.difficulty_rating if man and man.difficulty_rating else req.perceived_difficulty),
                    recent_error_sets=_recent_error_sets(db, user.id, r.exercise_id, config.persistent_error_sessions),
                )
            )
        outcome = decide_adaptations(
            plan_service.prescriptions_of(plan),
            performances,
            ws.day_index,
            plan_service.missed_sessions(db, user.id, plan, today),
            _recently_shortened(db, user.id, now),
            config,
        )
        guidance = outcome.guidance
        decisions_out = [AdaptationDecisionOut(**asdict(d)) for d in outcome.decisions]
        if outcome.changed:
            changed_reasons = [d.reason for d in outcome.decisions if d.changes]
            draft = PlanDraft(plan.template, plan.goal, plan.schedule, outcome.prescriptions, changed_reasons, plan.warnings or [])
            new_plan = plan_service.save_plan(
                db, user.id, draft, start_date=plan.start_date, parent=plan,
                reason_prefix=f"Adapted from plan version {plan.version} after session #{ws.id}:\n",
            )  # fmt: skip
            new_plan_id, applied = new_plan.id, True
        if outcome.decisions:
            db.add(
                AdaptationEvent(
                    user_id=user.id,
                    session_id=ws.id,
                    old_plan_id=plan.id,
                    new_plan_id=new_plan_id,
                    reason=" ".join(d.reason for d in outcome.decisions if d.changes) or "No changes: prescription maintained.",
                    details={
                        "actions": sorted({d.action for d in outcome.decisions}),
                        "decisions": [d.model_dump() for d in decisions_out],
                        "guidance": guidance,
                        "session_score": breakdown.session_score,
                    },
                )
            )

    db.commit()
    db.refresh(ws)
    return SessionCompleteResponse(
        session=SessionOut.model_validate(ws),
        adaptation_applied=applied,
        new_plan_id=new_plan_id,
        decisions=decisions_out,
        guidance=guidance,
    )
