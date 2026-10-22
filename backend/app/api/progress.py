from fastapi import APIRouter, Query, status
from sqlalchemy import select

from app.api.deps import AppSettings, CurrentUser, DbSession
from app.models import ProgressRecord
from app.schemas.progress import ProgressHistory, ProgressRecordIn, ProgressRecordOut, ProgressSummary
from app.services import progress_service

router = APIRouter(prefix="/api/progress", tags=["progress"])


@router.get("/summary", response_model=ProgressSummary)
def get_summary(user: CurrentUser, db: DbSession, settings: AppSettings) -> ProgressSummary:
    return progress_service.summary(db, user.id, settings)


@router.get("/history", response_model=ProgressHistory)
def get_history(user: CurrentUser, db: DbSession, limit: int = Query(default=50, ge=1, le=200)) -> ProgressHistory:
    return progress_service.history(db, user.id, limit)


@router.post("/records", response_model=ProgressRecordOut, status_code=status.HTTP_201_CREATED)
def upsert_record(body: ProgressRecordIn, user: CurrentUser, db: DbSession) -> ProgressRecord:
    record = db.scalar(select(ProgressRecord).where(ProgressRecord.user_id == user.id, ProgressRecord.date == body.date))
    if record is None:
        record = ProgressRecord(user_id=user.id, date=body.date)
        db.add(record)
    record.weight_kg = body.weight_kg
    record.notes = body.notes
    db.commit()
    db.refresh(record)
    return record
