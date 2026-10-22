from datetime import date

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentProfile, CurrentUser, DbSession
from app.models import Exercise, WorkoutPlan
from app.schemas.workout import ExerciseOut, PlanOut, TodayWorkoutOut
from app.services import plan_service
from app.services.recommender_service import PlanGenerationError

router = APIRouter(prefix="/api/workouts", tags=["workouts"])


@router.get("/exercises", response_model=list[ExerciseOut])
def list_exercises(db: DbSession, _user: CurrentUser) -> list[Exercise]:
    return list(db.scalars(select(Exercise).order_by(Exercise.id)))


@router.post("/generate", response_model=PlanOut, status_code=status.HTTP_201_CREATED)
def generate(profile: CurrentProfile, db: DbSession) -> PlanOut:
    try:
        plan = plan_service.generate_for_profile(db, profile)
    except PlanGenerationError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from None
    db.commit()
    db.refresh(plan)
    return plan_service.plan_out(plan)


@router.get("/active", response_model=PlanOut)
def active_plan(user: CurrentUser, db: DbSession) -> PlanOut:
    plan = plan_service.get_active_plan(db, user.id)
    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No active plan; generate one first")
    return plan_service.plan_out(plan)


@router.get("/today", response_model=TodayWorkoutOut)
def today_workout(user: CurrentUser, db: DbSession) -> TodayWorkoutOut:
    plan = plan_service.get_active_plan(db, user.id)
    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No active plan; generate one first")
    today = date.today()
    day_index = plan_service.day_index_for(plan, today)
    out = plan_service.plan_out(plan)
    completed_today = today in plan_service.completed_session_dates(db, user.id, today, today)
    return TodayWorkoutOut(
        date=today,
        plan_id=plan.id,
        is_training_day=day_index is not None,
        day=out.days[day_index] if day_index is not None else None,
        next_training_date=plan_service.next_training_date(plan, today),
        completed_today=completed_today,
    )


@router.get("/{plan_id}", response_model=PlanOut)
def get_plan(plan_id: int, user: CurrentUser, db: DbSession) -> PlanOut:
    plan = db.get(WorkoutPlan, plan_id)
    if plan is None or plan.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Plan not found")
    return plan_service.plan_out(plan)

