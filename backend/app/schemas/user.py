from pydantic import BaseModel, Field, field_validator

from app.schemas.common import (
    Allergen, DietaryPreference, Equipment, ExerciseSlug, Experience, Goal, HealthFlag, ORMModel, Sex, UTCDateTime,
)  # fmt: skip


class ProfileUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=80)
    age: int | None = Field(default=None, ge=13, le=100)
    sex: Sex = "unspecified"
    height_cm: float | None = Field(default=None, ge=100, le=250)
    weight_kg: float | None = Field(default=None, ge=30, le=300)
    goal: Goal = "general_fitness"
    experience: Experience = "beginner"
    equipment: list[Equipment] = Field(default_factory=list, max_length=5)
    days_per_week: int = Field(default=3, ge=1, le=6)
    preferred_days: list[int] = Field(default_factory=list, max_length=7)
    session_minutes: int = Field(default=30, ge=10, le=120)
    exclusions: list[ExerciseSlug] = Field(default_factory=list, max_length=5)
    dietary_preferences: list[DietaryPreference] = Field(default_factory=list, max_length=3)
    allergies: list[Allergen] = Field(default_factory=list, max_length=9)
    health_flags: list[HealthFlag] = Field(default_factory=list, max_length=5)

    @field_validator("preferred_days")
    @classmethod
    def valid_days(cls, v: list[int]) -> list[int]:
        if any(d < 0 or d > 6 for d in v):
            raise ValueError("preferred_days must be weekday numbers 0 (Monday) to 6 (Sunday)")
        return sorted(set(v))

    @field_validator("equipment", "exclusions", "dietary_preferences", "allergies", "health_flags")
    @classmethod
    def dedupe(cls, v: list) -> list:
        return sorted(set(v))

    @field_validator("display_name")
    @classmethod
    def strip_name(cls, v: str | None) -> str | None:
        return v.strip() or None if v is not None else None


class ProfileOut(ORMModel):
    display_name: str | None
    age: int | None
    sex: str
    height_cm: float | None
    weight_kg: float | None
    goal: str
    experience: str
    equipment: list[str]
    days_per_week: int
    preferred_days: list[int]
    session_minutes: int
    exclusions: list[str]
    dietary_preferences: list[str]
    allergies: list[str]
    health_flags: list[str]
    safety_acknowledged_at: UTCDateTime | None
    updated_at: UTCDateTime


class UserOut(ORMModel):
    id: int
    email: str
    is_guest: bool
    created_at: UTCDateTime
    profile: ProfileOut | None


class DeleteDataResponse(BaseModel):
    account_deleted: bool
    deleted: dict[str, int]
