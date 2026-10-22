from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # Throwaway account created by "continue as guest"; no password is ever issued for it.
    is_guest: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("0"))

    profile: Mapped["Profile | None"] = relationship(back_populates="user", uselist=False)


class Profile(Base):
    __tablename__ = "profiles"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    display_name: Mapped[str | None] = mapped_column(String(80))
    age: Mapped[int | None] = mapped_column(Integer)
    sex: Mapped[str] = mapped_column(String(16), default="unspecified")
    height_cm: Mapped[float | None] = mapped_column(Float)
    weight_kg: Mapped[float | None] = mapped_column(Float)
    goal: Mapped[str] = mapped_column(String(32), default="general_fitness")
    experience: Mapped[str] = mapped_column(String(16), default="beginner")
    equipment: Mapped[list[str]] = mapped_column(JSON, default=list)
    days_per_week: Mapped[int] = mapped_column(Integer, default=3)
    preferred_days: Mapped[list[int]] = mapped_column(JSON, default=list)
    session_minutes: Mapped[int] = mapped_column(Integer, default=30)
    exclusions: Mapped[list[str]] = mapped_column(JSON, default=list)
    dietary_preferences: Mapped[list[str]] = mapped_column(JSON, default=list)
    allergies: Mapped[list[str]] = mapped_column(JSON, default=list)
    health_flags: Mapped[list[str]] = mapped_column(JSON, default=list)
    safety_acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user: Mapped[User] = relationship(back_populates="profile")
