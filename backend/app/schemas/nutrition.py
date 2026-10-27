from datetime import date

from pydantic import BaseModel

from app.schemas.common import ORMModel


class FoodItemOut(ORMModel):
    id: int
    name: str
    serving_size: str
    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float
    fiber_g: float
    allergens: list[str]
    tags: list[str]
    meal_category: str


class FoodListOut(BaseModel):
    total: int
    items: list[FoodItemOut]
    disclaimer: str


class MealGuidanceOut(BaseModel):
    id: int
    date: date
    goal: str
    calorie_min: int | None
    calorie_max: int | None
    calorie_explanation: str
    protein_guidance: str
    meal_tips: list[str]
    applied_filters: dict
    suggested_foods: dict[str, list[FoodItemOut]]
    professional_referral: bool
    disclaimer: str


class BodyAssessmentOut(BaseModel):
    bmi: float | None
    category: str | None
    note: str


class MacroTargetsOut(BaseModel):
    calories: int
    protein_g: int
    carbs_g: int
    fat_g: int
    explanation: str


class PlanAlternativeOut(BaseModel):
    food_id: int
    name: str
    serving_size: str
    servings: float
    calories: int


class PlannedItemOut(BaseModel):
    food_id: int
    name: str
    serving_size: str
    servings: float
    role: str
    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float
    fiber_g: float
    alternatives: list[PlanAlternativeOut]


class PlannedMealOut(BaseModel):
    key: str
    label: str
    target_calories: int
    items: list[PlannedItemOut]
    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float
    fiber_g: float


class DayPlanOut(BaseModel):
    date: date
    meals: list[PlannedMealOut]
    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float
    fiber_g: float


class DietPlanOut(BaseModel):
    """A plan, or `available=false` with the reason it is withheld. Never partially filled."""

    available: bool
    reason: str | None
    body: BodyAssessmentOut
    targets: MacroTargetsOut | None
    days: list[DayPlanOut]
    tips: list[str]
    applied_filters: dict
    disclaimer: str
