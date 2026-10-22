from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models import Profile, User
from app.services.exercise_classifier import ModelRegistry

bearer = HTTPBearer(auto_error=False)

DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]


def user_from_token(db: Session, token: str | None) -> User | None:
    if not token:
        return None
    user_id = decode_access_token(token)
    return db.get(User, user_id) if user_id is not None else None


def get_current_user(
    db: DbSession, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]
) -> User:
    user = user_from_token(db, credentials.credentials if credentials else None)
    if user is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Invalid or expired credentials", headers={"WWW-Authenticate": "Bearer"}
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_profile(user: CurrentUser) -> Profile:
    if user.profile is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Complete your profile first")
    return user.profile


CurrentProfile = Annotated[Profile, Depends(require_profile)]


def get_registry(request: Request) -> ModelRegistry:
    return request.app.state.registry


Registry = Annotated[ModelRegistry, Depends(get_registry)]
