import secrets

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import DbSession
from app.core.security import create_access_token, hash_password, verify_password
from app.models import Profile, User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from app.services import plan_service

# Starter profile for guest accounts: bodyweight-only so every exercise is available without equipment.
GUEST_PROFILE = {
    "display_name": "Guest",
    "goal": "general_fitness",
    "experience": "beginner",
    "equipment": [],
    "days_per_week": 6,
    "preferred_days": [0, 1, 2, 3, 4, 5],
    "session_minutes": 30,
    "exclusions": [],
    "dietary_preferences": [],
    "allergies": [],
    "health_flags": [],
}

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Used to keep login timing similar whether or not the email exists.
_DUMMY_HASH = hash_password("timing-equaliser-0")


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, db: DbSession) -> TokenResponse:
    email = body.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
    user = User(email=email, password_hash=hash_password(body.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists") from None
    return TokenResponse(access_token=create_access_token(user.id))


@router.post("/guest", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def guest(db: DbSession) -> TokenResponse:
    """Create a throwaway account with a starter profile and plan, so the app can be tried in one click.

    The password is random and never returned, so the account can only be reached through this token.
    The safety notice is deliberately NOT pre-acknowledged — the user still reads it before a session.
    """
    user = User(
        email=f"guest-{secrets.token_hex(8)}@guest.invalid",
        password_hash=hash_password(secrets.token_urlsafe(32)),
        is_guest=True,
    )
    db.add(user)
    db.flush()
    db.add(Profile(user_id=user.id, **GUEST_PROFILE))
    db.flush()
    plan_service.generate_for_profile(db, db.get(Profile, user.id))
    db.commit()
    return TokenResponse(access_token=create_access_token(user.id))


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: DbSession) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    valid = verify_password(body.password, user.password_hash if user else _DUMMY_HASH)
    if not user or not valid:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    return TokenResponse(access_token=create_access_token(user.id))
