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
