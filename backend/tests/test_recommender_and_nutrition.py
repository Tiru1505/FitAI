import pytest

from app.services.exercise_catalog import CATALOG
from app.services.nutrition_service import estimate_calorie_range
from app.services.recommender_service import (
    ExerciseInfo, PlanGenerationError, ProfileInput, choose_schedule, estimate_minutes, generate_plan,
)  # fmt: skip

CATALOG_INFO = [ExerciseInfo(e["slug"], e["name"], e["equipment"]) for e in CATALOG]


def profile(**kw):
    base = dict(goal="general_fitness", experience="beginner", equipment=[], days_per_week=3, session_minutes=60)
    base.update(kw)
    return ProfileInput(**base)


def test_equipment_constraint_is_satisfied():
    draft = generate_plan(profile(equipment=[]), CATALOG_INFO)
    slugs = {p.exercise_slug for p in draft.prescriptions}
    assert slugs == {"squat", "lunge", "push_up"}
    assert any("needs" in r for r in draft.reasons)


def test_exclusions_are_respected():
    draft = generate_plan(profile(equipment=["dumbbells"], exclusions=["push_up", "lunge"]), CATALOG_INFO)
    assert {p.exercise_slug for p in draft.prescriptions} == {"squat", "biceps_curl", "shoulder_press"}


def test_no_exercises_left_raises():
    with pytest.raises(PlanGenerationError):
        generate_plan(profile(exclusions=["squat", "lunge", "push_up"]), CATALOG_INFO)


def test_muscle_gain_uses_upper_lower_split():
    draft = generate_plan(profile(goal="muscle_gain", equipment=["dumbbells"], days_per_week=4), CATALOG_INFO)
    assert draft.template == "upper_lower_split"
    day0 = {p.exercise_slug for p in draft.prescriptions if p.day_index == 0}
    day1 = {p.exercise_slug for p in draft.prescriptions if p.day_index == 1}
    assert day0 <= {"push_up", "shoulder_press", "biceps_curl"}
    assert day1 <= {"squat", "lunge"}


def test_session_length_is_respected():
    draft = generate_plan(profile(experience="advanced", equipment=["dumbbells"], session_minutes=15), CATALOG_INFO)
    for day in range(3):
        items = [p for p in draft.prescriptions if p.day_index == day]
        assert items
        assert sum(estimate_minutes(p.sets, p.repetitions, p.rest_seconds) for p in items) <= 15


def test_health_flags_force_beginner_and_warn():
    draft = generate_plan(profile(experience="advanced", health_flags=["injury"]), CATALOG_INFO)
    assert draft.warnings
    assert all(p.sets == 2 for p in draft.prescriptions)


def test_schedule_uses_preferred_days_then_defaults():
    assert choose_schedule(3, [5, 6]) == [0, 5, 6]
    assert choose_schedule(2, [1, 3, 5]) == [1, 3]
    assert choose_schedule(3, []) == [0, 2, 4]


def test_calorie_range_never_below_floor():
    est = estimate_calorie_range(30, "female", 150, 40, 1, "weight_management", [])
    assert est.calorie_min is not None and est.calorie_min >= 1200
    assert est.calorie_max > est.calorie_min


@pytest.mark.parametrize("flag", ["pregnancy", "eating_disorder_history", "chronic_condition", "special_diet"])
def test_calorie_range_withheld_for_sensitive_flags(flag):
    est = estimate_calorie_range(30, "male", 180, 80, 3, "weight_management", [flag])
    assert est.calorie_min is None and est.calorie_max is None


def test_calorie_range_withheld_for_minors_and_missing_data():
    assert estimate_calorie_range(16, "male", 180, 70, 3, "muscle_gain", []).calorie_min is None
    assert estimate_calorie_range(None, "male", 180, 70, 3, "muscle_gain", []).calorie_min is None


def test_food_table_is_traceable_usda_data():
    import csv

    from app.services.nutrition_service import FOODS_CSV

    rows = list(csv.DictReader(FOODS_CSV.open(encoding="utf-8")))
    assert len(rows) >= 100
    assert len({r["fdc_id"] for r in rows}) == len(rows)
    for r in rows:
        assert r["source"].startswith("USDA FoodData Central")
        assert r["fdc_id"].isdigit() and r["usda_description"]
        assert r["meal_category"] in {"breakfast", "lunch", "dinner", "snack"}
        tags = set(filter(None, r["dietary_tags"].split("|")))
        assert "vegan" not in tags or "vegetarian" in tags
        assert not ("vegan" in tags and set(r["allergens"].split("|")) & {"milk", "egg", "fish", "shellfish"})
        grams = float(r["serving_grams"])
        macros_kcal = 4 * float(r["protein_g"]) + 4 * float(r["carbohydrates_g"]) + 9 * float(r["fat_g"])
        # Atwater sanity check against USDA energy (loose: fibre, alcohol and specific factors differ)
        assert abs(macros_kcal - float(r["calories"])) <= max(25, 0.2 * float(r["calories"])), r["food_name"]
        assert grams > 0


def test_seed_foods_replaces_outdated_rows():
    from sqlalchemy import func, select

    from app.db.session import SessionLocal
    from app.models import FoodItem
    from app.services.nutrition_service import seed_foods

    with SessionLocal() as db:
        db.add(FoodItem(name="Outdated food", serving_size="1 g", calories=1, protein_g=0, carbs_g=0, fat_g=0, meal_category="snack"))
        db.commit()
        seed_foods(db)
        assert db.scalar(select(func.count()).where(FoodItem.name == "Outdated food")) == 0
        n = db.scalar(select(func.count(FoodItem.id)))
        seed_foods(db)  # unchanged CSV: no-op
        assert db.scalar(select(func.count(FoodItem.id))) == n
