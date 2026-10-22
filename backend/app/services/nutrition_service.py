"""General, educational nutrition guidance. Not a clinical or medical diet prescription."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import FoodItem

FOODS_CSV = Path(__file__).resolve().parents[1] / "data" / "foods.csv"

DISCLAIMER = (
    "Food values are from USDA FoodData Central (SR Legacy, 2018); dietary and allergen labels are assigned "
    "by FitAI and are not guarantees, so always check product labels. Values vary between brands and "
    "preparations and are for general education only. FitAI does not provide medical "
    "or clinical diet prescriptions. People with medical conditions, pregnancy, eating-disorder history, "
    "or special dietary requirements should consult a registered dietitian or doctor."
)

# Health flags for which no calorie numbers are shown at all.
REFER_FLAGS = {"pregnancy", "eating_disorder_history", "chronic_condition", "special_diet"}

GOAL_ADJUSTMENT = {  # (low, high) kcal relative to estimated maintenance
    "weight_management": (-500, -250),
    "muscle_gain": (150, 300),
    "general_fitness": (-100, 100),
    "endurance": (0, 200),
    "mobility": (-100, 100),
}

MEAL_GUIDANCE = {
    "weight_management": [
        "Build meals around vegetables, a protein source, and a moderate portion of whole grains.",
        "Prefer high-fibre foods, which tend to be more filling for the same energy.",
        "Aim for gradual change; avoid very low-calorie diets.",
    ],
    "muscle_gain": [
        "Include a protein source at each meal and spread protein across the day.",
        "Add energy-dense whole foods such as nuts, dairy or legumes if appetite is low.",
        "Eat a carbohydrate source around training to support performance.",
    ],
    "general_fitness": [
        "Use a balanced plate: half vegetables and fruit, a quarter protein, a quarter whole grains.",
        "Drink water regularly, especially around workouts.",
    ],
    "endurance": [
        "Carbohydrate-rich foods help fuel longer or more frequent sessions.",
        "Include protein and fluids after training to support recovery.",
    ],
    "mobility": [
        "Use a balanced plate: half vegetables and fruit, a quarter protein, a quarter whole grains.",
        "Stay hydrated throughout the day.",
    ],
}


@dataclass
class CalorieEstimate:
    calorie_min: int | None
    calorie_max: int | None
    explanation: str


def _round50(x: float) -> int:
    return int(round(x / 50.0) * 50)


def estimate_calorie_range(
    age: int | None, sex: str, height_cm: float | None, weight_kg: float | None,
    days_per_week: int, goal: str, health_flags: list[str],
) -> CalorieEstimate:  # fmt: skip
    if REFER_FLAGS & set(health_flags):
        return CalorieEstimate(None, None, "Calorie ranges are not shown for the health considerations you reported. Please consult a registered dietitian.")
    if age is not None and age < 18:
        return CalorieEstimate(None, None, "Calorie ranges are not provided for users under 18.")
    if not (age and height_cm and weight_kg):
        return CalorieEstimate(None, None, "Add age, height and weight to your profile to see an approximate range.")

    sex_term = {"male": 5.0, "female": -161.0}.get(sex, -78.0)  # unspecified: midpoint of the two
    bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age + sex_term  # Mifflin-St Jeor
    activity = 1.375 if days_per_week <= 2 else 1.55 if days_per_week <= 4 else 1.725
    maintenance = bmr * activity
    low_adj, high_adj = GOAL_ADJUSTMENT.get(goal, (-100, 100))
    floor = max(1500.0 if sex == "male" else 1200.0, bmr)
    low = max(floor, maintenance + low_adj)
    high = max(low + 100, maintenance + high_adj)
    return CalorieEstimate(
        _round50(low),
        _round50(high),
        "Approximate range from the Mifflin-St Jeor equation, an activity factor based on training days, "
        "and a moderate goal adjustment. The lower bound never goes below your estimated resting energy needs.",
    )


def protein_guidance(weight_kg: float | None, goal: str) -> str:
    if not weight_kg:
        return "Include a source of protein at each meal."
    low, high = (1.6, 2.0) if goal == "muscle_gain" else (1.2, 1.6)
    return (
        f"A commonly cited general range for active adults is about {low}-{high} g of protein per kg of body "
        f"weight, roughly {round(weight_kg * low)}-{round(weight_kg * high)} g per day. Confirm with a professional if you have kidney disease or other conditions."
    )


def seed_foods(db: Session) -> None:
    """Load foods.csv, replacing the table when the CSV content has changed (no other table references foods)."""
    with FOODS_CSV.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    current = [(i.name, i.serving_size, i.calories) for i in db.scalars(select(FoodItem).order_by(FoodItem.id))]
    wanted = [(r["food_name"], r["serving_size"], float(r["calories"])) for r in rows]
    if current == wanted:
        return
    if db.scalar(select(func.count(FoodItem.id))):
        db.execute(delete(FoodItem))
    for row in rows:
        db.add(
            FoodItem(
                name=row["food_name"],
                serving_size=row["serving_size"],
                calories=float(row["calories"]),
                protein_g=float(row["protein_g"]),
                carbs_g=float(row["carbohydrates_g"]),
                fat_g=float(row["fat_g"]),
                fiber_g=float(row["fiber_g"]),
                allergens=[a for a in row["allergens"].split("|") if a],
                tags=[t for t in row["dietary_tags"].split("|") if t],
                meal_category=row["meal_category"],
            )
        )
    db.commit()


def filter_foods(
    db: Session, *, diet: str | None, exclude_allergens: list[str], meal_category: str | None,
    max_calories: float | None, min_protein_g: float | None, query: str | None, limit: int, offset: int,
) -> tuple[int, list[FoodItem]]:  # fmt: skip
    stmt = select(FoodItem)
    if meal_category:
        stmt = stmt.where(FoodItem.meal_category == meal_category)
    if max_calories is not None:
        stmt = stmt.where(FoodItem.calories <= max_calories)
    if min_protein_g is not None:
        stmt = stmt.where(FoodItem.protein_g >= min_protein_g)
    if query:
        stmt = stmt.where(FoodItem.name.ilike(f"%{query}%"))
    items = list(db.scalars(stmt.order_by(FoodItem.name)))
    # JSON list filters are applied in Python so they behave identically on SQLite and PostgreSQL.
    if diet:
        items = [i for i in items if diet in i.tags]
    if exclude_allergens:
        blocked = set(exclude_allergens)
        items = [i for i in items if not blocked & set(i.allergens)]
    return len(items), items[offset : offset + limit]
