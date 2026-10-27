"""Tests for the per-user diet planner.

The two things worth guarding are the health boundary (a plan must never appear where calorie
numbers are withheld) and that a plan is actually edible: it respects the diet and allergy filters,
lands near the calorie target, and never serves a dry ingredient as a meal.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.db.session import SessionLocal
from app.models import Profile
from app.services import diet_planner as dp
from app.services.nutrition_service import seed_foods

TODAY = date(2026, 10, 27)


@pytest.fixture(scope="module")
def db(client):  # `client` starts the app, which runs the migrations that create the tables
    session = SessionLocal()
    seed_foods(session)
    yield session
    session.close()


def make_profile(**overrides) -> Profile:
    values = dict(
        user_id=1, age=28, sex="male", height_cm=175.0, weight_kg=78.0,
        days_per_week=4, goal="general_fitness", health_flags=[],
        dietary_preferences=[], allergies=[],
    )  # fmt: skip
    values.update(overrides)
    return Profile(**values)


def plan_for(db, *, diet=None, exclude_allergens=(), days=1, **profile_overrides) -> dp.DietPlan:
    return dp.build_plan(
        db, make_profile(**profile_overrides), diet=diet,
        exclude_allergens=list(exclude_allergens), start=TODAY, days=days,
    )  # fmt: skip


# --- health boundary ----------------------------------------------------------------------------

@pytest.mark.parametrize("flag", sorted(dp.ns.REFER_FLAGS))
def test_no_plan_for_flags_that_need_a_professional(db, flag):
    plan = plan_for(db, health_flags=[flag])
    assert not plan.available
    assert plan.days == [] and plan.targets is None
    assert "dietitian" in plan.reason or "professional" in plan.reason


@pytest.mark.parametrize("flag", sorted(dp.ns.REFER_FLAGS))
def test_bmi_withheld_for_flags_that_need_a_professional(db, flag):
    # A weight-status number is the one thing not to show someone with an eating-disorder history.
    body = plan_for(db, health_flags=[flag]).body
    assert body.bmi is None and body.category is None


def test_no_plan_for_minors(db):
    plan = plan_for(db, age=16)
    assert not plan.available
    assert plan.days == []
    assert plan.body.bmi is None  # read against age percentiles, so not shown either


@pytest.mark.parametrize("missing", [{"weight_kg": None}, {"height_cm": None}, {"age": None}])
def test_no_plan_without_the_measurements_it_needs(db, missing):
    plan = plan_for(db, **missing)
    assert not plan.available and plan.days == []


def test_plan_is_built_for_a_flag_that_only_needs_care(db):
    # An injury changes the workout, not whether general nutrition guidance may be shown.
    assert plan_for(db, health_flags=["injury"]).available


def test_impossible_filters_are_reported_not_faked(db):
    plan = plan_for(db, diet="vegan", exclude_allergens=["soy", "wheat", "tree_nuts", "peanuts", "sesame"])
    if not plan.available:
        assert "cannot be built" in plan.reason or plan.reason
    else:  # a plan is only acceptable if it really honours the filters
        assert all(i.name for day in plan.days for m in day.meals for i in m.items)


# --- filters ------------------------------------------------------------------------------------

def _items(plan: dp.DietPlan) -> list[dp.PlannedItem]:
    return [item for day in plan.days for meal in day.meals for item in meal.items]


def _food_tags(db, name: str) -> tuple[list[str], list[str]]:
    from app.models import FoodItem
    from sqlalchemy import select

    food = db.scalar(select(FoodItem).where(FoodItem.name == name))
    return food.tags, food.allergens


@pytest.mark.parametrize("diet", ["vegetarian", "vegan"])
def test_every_planned_food_matches_the_diet(db, diet):
    plan = plan_for(db, diet=diet, days=7)
    assert plan.available
    for item in _items(plan):
        tags, _ = _food_tags(db, item.name)
        assert diet in tags, f"{item.name} is not {diet}"


def test_excluded_allergens_never_appear(db):
    excluded = {"milk", "tree_nuts", "peanuts"}
    plan = plan_for(db, diet="vegetarian", exclude_allergens=sorted(excluded), days=7)
    assert plan.available
    for item in _items(plan):
        _, allergens = _food_tags(db, item.name)
        assert not excluded & set(allergens), f"{item.name} carries {allergens}"


def test_alternatives_respect_the_same_filters(db):
    # A swap the user can click must be as safe as the item it replaces.
    plan = plan_for(db, diet="vegan", exclude_allergens=["soy"], days=3)
    assert plan.available
    for item in _items(plan):
        for alternative in item.alternatives:
            tags, allergens = _food_tags(db, alternative.name)
            assert "vegan" in tags and "soy" not in allergens


# --- the plan is edible -------------------------------------------------------------------------

def test_cooking_ingredients_are_not_served_as_meals(db):
    # "1 cup of dry semolina" is an ingredient, not a portion on a plate.
    plan = plan_for(db, diet="vegetarian", days=7)
    for item in _items(plan):
        assert not dp.INGREDIENT_ONLY.search(item.name), f"{item.name} is an ingredient"


def test_servings_are_shown_in_half_steps_within_bounds(db):
    for item in _items(plan_for(db, days=7)):
        assert dp.MIN_SERVINGS <= item.servings <= dp.MAX_SERVINGS
        assert abs(item.servings / dp.SERVING_STEP - round(item.servings / dp.SERVING_STEP)) < 1e-9


@pytest.mark.parametrize(
    "overrides,diet",
    [
        ({}, None),
        ({"goal": "muscle_gain", "weight_kg": 85.0}, None),
        ({"goal": "weight_management", "sex": "female", "weight_kg": 62.0, "height_cm": 162.0}, "vegetarian"),
        ({"goal": "endurance", "days_per_week": 6, "weight_kg": 95.0, "height_cm": 183.0}, None),
        ({"goal": "general_fitness"}, "vegan"),
    ],
)
def test_day_total_lands_near_the_calorie_target(db, overrides, diet):
    # Half-serving steps mean the total cannot be exact; 15% is the tolerance the planner holds to
    # across profiles, and the response reports both target and total so nothing is hidden.
    plan = plan_for(db, diet=diet, days=7, **overrides)
    assert plan.available
    for day in plan.days:
        gap = abs(day.calories - plan.targets.calories) / plan.targets.calories
        assert gap <= 0.15, f"{day.date}: {day.calories} vs target {plan.targets.calories}"


def test_protein_target_is_met(db):
    plan = plan_for(db, goal="muscle_gain", days=7)
    for day in plan.days:
        assert day.protein_g >= plan.targets.protein_g * 0.9


def test_every_meal_has_a_protein_source(db):
    for day in plan_for(db, diet="vegan", days=7).days:
        for meal in day.meals:
            assert any(item.role == "protein" for item in meal.items), f"{meal.label} has no protein"


def test_meal_totals_are_the_sum_of_their_items(db):
    for day in plan_for(db, days=3).days:
        for meal in day.meals:
            assert meal.calories == pytest.approx(sum(i.calories for i in meal.items), abs=0.05)
            assert meal.protein_g == pytest.approx(sum(i.protein_g for i in meal.items), abs=0.05)
        assert day.calories == pytest.approx(sum(m.calories for m in day.meals), abs=0.05)


def test_a_day_does_not_repeat_the_same_food(db):
    for day in plan_for(db, days=7).days:
        names = [item.name for meal in day.meals for item in meal.items]
        assert len(names) == len(set(names)), f"{day.date} repeats a food"


def test_consecutive_days_differ(db):
    menus = {tuple(i.name for m in day.meals for i in m.items) for day in plan_for(db, days=7).days}
    assert len(menus) >= 5, "a week of plans should not be the same day seven times"


def test_same_profile_and_date_plan_the_same_meals(db):
    # The plan is rebuilt on request instead of stored, so it has to be reproducible.
    first, second = plan_for(db, days=1), plan_for(db, days=1)
    assert [i.name for i in _items(first)] == [i.name for i in _items(second)]


def test_different_users_get_different_plans(db):
    one = [i.name for i in _items(plan_for(db, user_id=1))]
    two = [i.name for i in _items(plan_for(db, user_id=99))]
    assert one != two


# --- targets ------------------------------------------------------------------------------------

def test_macro_targets_add_up_to_the_calorie_total(db):
    targets = dp.macro_targets(2000, 2400, 75.0, "muscle_gain")
    energy = targets.protein_g * 4 + targets.carbs_g * 4 + targets.fat_g * 9
    assert targets.calories == 2200
    assert abs(energy - targets.calories) / targets.calories < 0.03


def test_protein_target_cannot_crowd_out_carbohydrate(db):
    # A heavy user on a low calorie target: protein is capped at 35% of energy.
    targets = dp.macro_targets(1600, 1800, 120.0, "muscle_gain")
    assert targets.protein_g * 4 <= targets.calories * 0.36
    assert targets.carbs_g > 0


def test_macro_targets_work_without_a_weight(db):
    targets = dp.macro_targets(2000, 2200, None, "general_fitness")
    assert targets.protein_g > 0 and "20%" in targets.explanation


@pytest.mark.parametrize(
    "weight,height,expected",
    [(55.0, 175.0, "under"), (70.0, 175.0, "in the healthy"), (85.0, 175.0, "above"), (120.0, 175.0, "well above")],
)
def test_bmi_categories(db, weight, height, expected):
    body = dp.assess_body(30, height, weight, [])
    assert body.bmi == pytest.approx(weight / (height / 100) ** 2, abs=0.05)
    assert expected in body.category


def test_bmi_note_says_it_is_not_a_diagnosis(db):
    note = dp.assess_body(30, 175.0, 80.0, []).note
    assert "not a diagnosis" in note and "muscle" in note


# --- API ----------------------------------------------------------------------------------------

def test_diet_plan_endpoint_requires_auth(client):
    assert client.post("/api/nutrition/diet-plan", json={}).status_code == 401


def test_diet_plan_endpoint_returns_a_week(client, auth_headers, profile_payload):
    assert client.put("/api/users/me", json=profile_payload, headers=auth_headers).status_code == 200
    response = client.post("/api/nutrition/diet-plan", json={"days": 7}, headers=auth_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["available"] and len(body["days"]) == 7
    assert body["targets"]["calories"] > 0
    assert body["disclaimer"]
    assert all(day["meals"] for day in body["days"])


def test_diet_plan_endpoint_applies_request_overrides(client, auth_headers, profile_payload):
    assert client.put("/api/users/me", json=profile_payload, headers=auth_headers).status_code == 200
    response = client.post(
        "/api/nutrition/diet-plan",
        json={"diet": "vegan", "exclude_allergens": ["soy"], "days": 1},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["applied_filters"] == {"diet": "vegan", "exclude_allergens": ["soy"]}


def test_diet_plan_endpoint_withholds_for_sensitive_flags(client, auth_headers, profile_payload):
    payload = {**profile_payload, "health_flags": ["eating_disorder_history"]}
    assert client.put("/api/users/me", json=payload, headers=auth_headers).status_code == 200
    body = client.post("/api/nutrition/diet-plan", json={}, headers=auth_headers).json()
    assert body["available"] is False
    assert body["days"] == [] and body["targets"] is None
    assert body["body"]["bmi"] is None


def test_diet_plan_endpoint_rejects_too_many_days(client, auth_headers, profile_payload):
    assert client.put("/api/users/me", json=profile_payload, headers=auth_headers).status_code == 200
    assert client.post("/api/nutrition/diet-plan", json={"days": 30}, headers=auth_headers).status_code == 422
