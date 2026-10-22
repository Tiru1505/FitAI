from datetime import date

from fastapi import APIRouter, HTTPException, status

from app.api.deps import AppSettings, CurrentUser, DbSession
from app.models import WorkoutPlan, WorkoutSession
from app.schemas.session import LiveResultsOut, SessionCompleteRequest, SessionCompleteResponse, SessionOut, SessionStartRequest
from app.services import live_session_store, plan_service
from app.services.session_service import complete_session

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


def owned_session(db, user, session_id: int) -> WorkoutSession:
    ws = db.get(WorkoutSession, session_id)
    if ws is None or ws.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    return ws


@router.post("/start", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
def start_session(body: SessionStartRequest, user: CurrentUser, db: DbSession) -> WorkoutSession:
    if user.profile is None or user.profile.safety_acknowledged_at is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Please read and acknowledge the safety information first")
    plan = db.get(WorkoutPlan, body.plan_id) if body.plan_id else plan_service.get_active_plan(db, user.id)
    if body.plan_id and (plan is None or plan.user_id != user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Plan not found")
    day_index = body.day_index
    if plan is not None and day_index is None:
        day_index = plan_service.day_index_for(plan, date.today())
    if plan is not None and day_index is not None and day_index >= len(plan.schedule):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "day_index is outside this plan's schedule")
    ws = WorkoutSession(user_id=user.id, plan_id=plan.id if plan else None, day_index=day_index)
    db.add(ws)
    db.commit()
    db.refresh(ws)
    return ws


@router.get("/{session_id}", response_model=SessionOut)
def get_session(session_id: int, user: CurrentUser, db: DbSession) -> WorkoutSession:
    return owned_session(db, user, session_id)


@router.get("/{session_id}/live-results", response_model=LiveResultsOut)
def live_results(session_id: int, user: CurrentUser, db: DbSession) -> LiveResultsOut:
    owned_session(db, user, session_id)
    return LiveResultsOut(session_id=session_id, exercises=live_session_store.get(session_id))


@router.post("/{session_id}/complete", response_model=SessionCompleteResponse)
def complete(
    session_id: int, body: SessionCompleteRequest, user: CurrentUser, db: DbSession, settings: AppSettings
) -> SessionCompleteResponse:
    ws = owned_session(db, user, session_id)
    if ws.status != "in_progress":
        raise HTTPException(status.HTTP_409_CONFLICT, "Session is already completed")
    return complete_session(db, user, ws, body, settings)
