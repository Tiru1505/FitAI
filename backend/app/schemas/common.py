from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict

# SQLite returns naive datetimes; all stored timestamps are UTC, so mark them explicitly for clients.
UTCDateTime = Annotated[datetime, AfterValidator(lambda d: d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d)]

ExerciseSlug = Literal["squat", "lunge", "push_up", "biceps_curl", "shoulder_press"]
Goal = Literal["general_fitness", "weight_management", "muscle_gain", "endurance", "mobility"]
Experience = Literal["beginner", "intermediate", "advanced"]
Equipment = Literal["dumbbells", "resistance_band"]
Sex = Literal["female", "male", "unspecified"]
HealthFlag = Literal["injury", "chronic_condition", "pregnancy", "eating_disorder_history", "special_diet"]
DietaryPreference = Literal["vegetarian", "vegan", "gluten_free"]
Allergen = Literal["milk", "egg", "fish", "shellfish", "tree_nuts", "peanuts", "wheat", "soy", "sesame"]
MealCategory = Literal["breakfast", "lunch", "dinner", "snack"]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)
