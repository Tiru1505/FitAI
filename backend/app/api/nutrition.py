from datetime import date

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.api.deps import CurrentProfile, CurrentUser, DbSession
from app.models import MealGuidance
from app.schemas.common import Allergen, DietaryPreference, MealCategory
from app.schemas.nutrition import FoodItemOut, FoodListOut, MealGuidanceOut
from app.services import nutrition_service as ns

router = APIRouter(prefix="/api/nutrition", tags=["nutrition"])


@router.get("/foods", response_model=FoodListOut)
def list_foods(
    db: DbSession,
    _user: CurrentUser,
    diet: DietaryPreference | None = None,
    exclude_allergens: list[Allergen] = Query(default=[]),
    meal_category: MealCategory | None = None,
    max_calories: float | None = Query(default=None, ge=0, le=5000),
    min_protein_g: float | None = Query(default=None, ge=0, le=500),
    q: str | None = Query(default=None, max_length=60),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> FoodListOut:
    total, items = ns.filter_foods(
        db, diet=diet, exclude_allergens=exclude_allergens, meal_category=meal_category,
        max_calories=max_calories, min_protein_g=min_protein_g, query=q, limit=limit, offset=offset,
    )  # fmt: skip
    return FoodListOut(total=total, items=[FoodItemOut.model_validate(i) for i in items], disclaimer=ns.DISCLAIMER)


class MealGuidanceRequest(BaseModel):
    # Optional overrides; by default the profile's dietary preferences and allergies are used.
    diet: DietaryPreference | None = None
    exclude_allergens: list[Allergen] | None = Field(default=None, max_length=9)


@router.post("/meal-guidance", response_model=MealGuidanceOut)
def meal_guidance(body: MealGuidanceRequest, profile: CurrentProfile, db: DbSession) -> MealGuidanceOut:
    estimate = ns.estimate_calorie_range(
        profile.age, profile.sex, profile.height_cm, profile.weight_kg,
        profile.days_per_week, profile.goal, profile.health_flags or [],
    )  # fmt: skip
    prefs = profile.dietary_preferences or []
    diet = body.diet or ("vegan" if "vegan" in prefs else "vegetarian" if "vegetarian" in prefs else None)
    allergens = body.exclude_allergens if body.exclude_allergens is not None else (profile.allergies or [])
    if "gluten_free" in prefs and "wheat" not in allergens:
        allergens = [*allergens, "wheat"]

    suggestions: dict[str, list[FoodItemOut]] = {}
    for category in ("breakfast", "lunch", "dinner", "snack"):
        _, items = ns.filter_foods(
            db, diet=diet, exclude_allergens=allergens, meal_category=category,
            max_calories=None, min_protein_g=None, query=None, limit=200, offset=0,
        )  # fmt: skip
        items.sort(key=lambda f: (-(f.protein_g / max(f.calories, 1)) if profile.goal == "muscle_gain" else -f.fiber_g))
        suggestions[category] = [FoodItemOut.model_validate(i) for i in items[:6]]

    tips = ns.MEAL_GUIDANCE.get(profile.goal, ns.MEAL_GUIDANCE["general_fitness"])
    record = MealGuidance(
        user_id=profile.user_id, date=date.today(), goal=profile.goal,
        calorie_min=estimate.calorie_min, calorie_max=estimate.calorie_max, notes=estimate.explanation,
    )  # fmt: skip
    db.add(record)
    db.commit()
    return MealGuidanceOut(
        id=record.id,
        date=record.date,
        goal=profile.goal,
        calorie_min=estimate.calorie_min,
        calorie_max=estimate.calorie_max,
        calorie_explanation=estimate.explanation,
        protein_guidance=ns.protein_guidance(profile.weight_kg, profile.goal),
        meal_tips=tips,
        applied_filters={"diet": diet, "exclude_allergens": sorted(allergens)},
        suggested_foods=suggestions,
        professional_referral=bool(profile.health_flags),
        disclaimer=ns.DISCLAIMER,
    )
