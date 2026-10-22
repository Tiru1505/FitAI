from datetime import datetime, timezone

from fastapi import APIRouter, Query

from app.api.deps import CurrentProfile, CurrentUser, DbSession
from app.models import Profile
from app.schemas.user import DeleteDataResponse, ProfileOut, ProfileUpdate, UserOut
from app.services.user_data_service import delete_user_data

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("/me", response_model=UserOut)
def get_me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


@router.put("/me", response_model=UserOut)
def update_me(body: ProfileUpdate, user: CurrentUser, db: DbSession) -> UserOut:
    profile = user.profile
    if profile is None:
        profile = Profile(user_id=user.id)
        db.add(profile)
    for key, value in body.model_dump().items():
        setattr(profile, key, value)
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)


@router.post("/me/safety-acknowledgement", response_model=ProfileOut)
def acknowledge_safety(profile: CurrentProfile, db: DbSession) -> ProfileOut:
    profile.safety_acknowledged_at = datetime.now(timezone.utc)
    db.commit()
    return ProfileOut.model_validate(profile)


@router.delete("/me/data", response_model=DeleteDataResponse)
def delete_my_data(
    user: CurrentUser,
    db: DbSession,
    keep_account: bool = Query(default=False, description="Keep the login but delete profile, plans, sessions and records"),
) -> DeleteDataResponse:
    counts = delete_user_data(db, user, delete_account=not keep_account)
    return DeleteDataResponse(account_deleted=not keep_account, deleted=counts)
