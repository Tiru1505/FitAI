"""Builds a day of meals from the food table to fit a user's energy and protein targets.

General educational guidance, not a clinical diet prescription. The health guards in
`nutrition_service.estimate_calorie_range` decide whether a plan may be produced at all: when no
calorie range is available (under-18, a health flag needing a professional, or an incomplete
profile) this module returns an unavailable plan with the reason instead of inventing numbers.

The planner is deliberately transparent rather than optimal. For each meal it:

1. splits the day's calorie and protein targets across meals by a fixed share,
2. fills three roles - a protein anchor, a carbohydrate base, a vegetable or fruit,
3. scales each food to a whole or half serving to approach the meal's targets,

and reports the gap it could not close. Every item carries the role it was chosen for and a few
same-role alternatives, so the user can see why a food is there and swap it.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field, replace
from datetime import date

from sqlalchemy.orm import Session

from app.models import FoodItem, Profile
from app.services import nutrition_service as ns


@dataclass(frozen=True)
class MealSlot:
    key: str
    label: str
    share: float  # of the day's calories
    roles: tuple[str, ...]


# Shares sum to 1.0. Snacks cover everything eaten outside the three meals.
# The LAST role of each meal is the balancer: it is sized to close whatever calorie gap the other
# items leave, which is why the carbohydrate base comes last in the main meals - carbohydrate is
# also the remainder in the macro split, so the two agree.
MEAL_SLOTS: tuple[MealSlot, ...] = (
    MealSlot("breakfast", "Breakfast", 0.25, ("protein", "fruit", "fat", "carb")),
    MealSlot("lunch", "Lunch", 0.30, ("protein", "vegetable", "fat", "carb")),
    MealSlot("dinner", "Dinner", 0.30, ("protein", "vegetable", "fat", "carb")),
    MealSlot("snack", "Snacks", 0.15, ("fruit", "protein", "fat")),
)

# Share of calories from fat. The rest, after protein, goes to carbohydrate.
FAT_FRACTION = 0.275
# Protein grams per kg of body weight, by goal. Same ranges as the written protein guidance.
PROTEIN_PER_KG = {"muscle_gain": 1.8, "endurance": 1.5}
PROTEIN_PER_KG_DEFAULT = 1.4
# Servings are shown in half steps within these bounds; anything else reads as a false precision.
MIN_SERVINGS, MAX_SERVINGS, SERVING_STEP = 0.5, 3.0, 0.5
# A protein anchor may not eat more than this share of its meal's calories.
ANCHOR_CALORIE_SHARE = 0.6
# The anchor covers most of the meal's protein; the rest arrives with the other items, which is why
# sizing it to the full target overshoots.
ANCHOR_PROTEIN_SHARE = 0.7
# Calories aimed at the vegetable or fruit on the side, and the bounds it is held within.
SIDE_CALORIES, SIDE_MIN, SIDE_MAX = 110.0, 1.0, 2.0
# How many of the best-ranked candidates to choose at random from, for day-to-day variety.
VARIETY_POOL = 6
# A role's own pool must offer at least this many candidates, or the search widens to all foods.
MIN_ROLE_CANDIDATES = 3

# Foods that are cooking ingredients rather than servings. They stay in the food explorer, where
# looking up the energy in 100 g of flour is useful, but "1 cup of dry semolina" is not a meal.
INGREDIENT_ONLY = re.compile(r"\b(flour|atta|besan|semolina|sooji|gluten|starch|yeast|baking)\b|, dry\b", re.I)

# WHO adult BMI categories. Descriptive only: BMI ignores body composition, so a muscular person
# can read as "overweight" while being perfectly healthy.
BMI_BANDS = ((18.5, "under the healthy-weight range"), (25.0, "in the healthy-weight range"),
             (30.0, "above the healthy-weight range"), (float("inf"), "well above the healthy-weight range"))
BMI_NOTE = (
    "BMI is a population screening number, not a diagnosis. It does not distinguish muscle from fat, "
    "so trained people often read high. Use it as one rough input among many, and ask a doctor or "
    "dietitian about your own situation."
)


@dataclass(frozen=True)
class BodyAssessment:
    bmi: float | None
    category: str | None
    note: str


@dataclass(frozen=True)
class MacroTargets:
    calories: int
    protein_g: int
    carbs_g: int
    fat_g: int
    explanation: str


@dataclass(frozen=True)
class Alternative:
    food_id: int
    name: str
    serving_size: str
    servings: float
    calories: int


@dataclass(frozen=True)
class PlannedItem:
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
    alternatives: list[Alternative] = field(default_factory=list)


@dataclass(frozen=True)
class PlannedMeal:
    key: str
    label: str
    target_calories: int
    items: list[PlannedItem]
    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float
    fiber_g: float


@dataclass(frozen=True)
class DayPlan:
    date: date
    meals: list[PlannedMeal]
    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float
    fiber_g: float


@dataclass(frozen=True)
class DietPlan:
    available: bool
    reason: str | None
    body: BodyAssessment
    targets: MacroTargets | None
    days: list[DayPlan]
    tips: list[str]
    applied_filters: dict
    disclaimer: str


def assess_body(age: int | None, height_cm: float | None, weight_kg: float | None,
                health_flags: list[str]) -> BodyAssessment:
    """BMI and its WHO band, withheld where the number would do more harm than good.

    The flags that withhold calorie numbers withhold BMI as well. For someone with a history of an
    eating disorder, a weight-status number is the very thing not to put on screen; for pregnancy,
    adult BMI bands do not apply. Under-18 BMI is read against age and sex percentiles.
    """
    if ns.REFER_FLAGS & set(health_flags):
        return BodyAssessment(None, None, "BMI is not shown for the health considerations you reported. Please speak to a doctor or registered dietitian.")
    if not (height_cm and weight_kg):
        return BodyAssessment(None, None, "Add your height and weight to see your BMI.")
    if age is not None and age < 18:
        return BodyAssessment(None, None, "BMI for under-18s is read against age and sex percentiles, so it is not shown here.")
    bmi = weight_kg / (height_cm / 100.0) ** 2
    category = next(label for limit, label in BMI_BANDS if bmi < limit)
    return BodyAssessment(round(bmi, 1), category, BMI_NOTE)


def macro_targets(calorie_min: int, calorie_max: int, weight_kg: float | None, goal: str) -> MacroTargets:
    """Split the middle of the calorie range into protein, fat and carbohydrate."""
    calories = (calorie_min + calorie_max) / 2.0
    per_kg = PROTEIN_PER_KG.get(goal, PROTEIN_PER_KG_DEFAULT)
    # Without a weight, fall back to a share of energy rather than refusing to plan.
    protein_g = weight_kg * per_kg if weight_kg else calories * 0.20 / 4.0
    # Protein is capped so it cannot crowd out the carbohydrate a training diet needs.
    protein_g = min(protein_g, calories * 0.35 / 4.0)
    fat_g = calories * FAT_FRACTION / 9.0
    carbs_g = max(0.0, (calories - protein_g * 4 - fat_g * 9) / 4.0)
    basis = f"{per_kg} g per kg of body weight" if weight_kg else "20% of calories"
    return MacroTargets(
        calories=round(calories),
        protein_g=round(protein_g),
        carbs_g=round(carbs_g),
        fat_g=round(fat_g),
        explanation=(
            f"Calories are the middle of your estimated range. Protein comes from {basis}, fat from "
            f"{round(FAT_FRACTION * 100)}% of calories, and carbohydrate makes up the rest. These are "
            "general training-diet proportions, not a prescription."
        ),
    )


# --- role fitness -------------------------------------------------------------------------------
# Each role scores a food on how well it plays that part. Scores are only used to rank candidates.

def _energy(food: FoodItem) -> float:
    return max(food.calories, 1.0)


def _protein_score(food: FoodItem) -> float:
    return food.protein_g * 4 / _energy(food)


def _carb_fraction(food: FoodItem) -> float:
    return food.carbs_g * 4 / _energy(food)


def _fibre_score(food: FoodItem) -> float:
    return food.fiber_g / _energy(food) * 100


def _fat_fraction(food: FoodItem) -> float:
    return food.fat_g * 9 / _energy(food)


# Sauces, soups and juices are real foods but not a vegetable or fruit on the side of a plate.
NOT_PRODUCE = re.compile(r"\b(sauce|soup|juice|gravy|ketchup|salsa|dip|paste|pickle)\b", re.I)


def _is_produce(food: FoodItem) -> bool:
    return not NOT_PRODUCE.search(food.name)


ROLE_RULES = {
    # role: (eligibility, ranking score)
    "protein": (lambda f: f.protein_g >= 6 and _protein_score(f) >= 0.18, _protein_score),
    # Ranked by carbohydrate GRAMS, not by carbohydrate share of calories: nearly all of a berry's
    # calories are carbohydrate, so ranking by share puts fruit above the rice and bread that
    # actually make a staple portion.
    # Scored as carbohydrate net of protein, so grains come before pulses. Pulses are already the
    # protein anchor in a vegetarian plan, and using them for the carbohydrate base as well pushed
    # protein well past target.
    "carb": (lambda f: _carb_fraction(f) >= 0.45 and f.calories >= 80, lambda f: f.carbs_g - f.protein_g),
    # Fruit and vegetable are separated by how sugary and how protein-poor they are, since the food
    # table has no food-group column: without this, bean sprouts outrank berries on fibre.
    "vegetable": (lambda f: f.fiber_g >= 1.0 and f.calories <= 200 and _carb_fraction(f) < 0.70
                  and _is_produce(f), _fibre_score),
    "fruit": (lambda f: f.fiber_g >= 1.0 and f.calories <= 250 and _carb_fraction(f) >= 0.70
              and _protein_score(f) < 0.20 and _is_produce(f), _fibre_score),
    # Mostly-fat foods only. The protein test keeps salmon, eggs and tofu out of this slot - they
    # belong in the protein role, and letting them fill it too pushed protein far over target.
    # Ranking by fibre puts nuts and seeds above oils and butter, which carry nothing else.
    "fat": (lambda f: _fat_fraction(f) >= 0.6 and f.fat_g >= 3 and _protein_score(f) < 0.25, _fibre_score),
}
# Which meal categories each role is drawn from. Roles are not confined to the meal being built:
# fruit lives in the snack category and vegetables in the dinner category, so a breakfast asking
# for fruit must look outside breakfast or it ends up with a second slice of bread.
ROLE_SOURCES = {
    "fruit": ("snack", "breakfast"),
    "vegetable": ("dinner", "lunch"),
    "fat": ("snack", "breakfast", "lunch", "dinner"),
}


def _round_servings(value: float) -> float:
    stepped = round(value / SERVING_STEP) * SERVING_STEP
    return min(MAX_SERVINGS, max(MIN_SERVINGS, stepped))


def _scaled(food: FoodItem, servings: float, role: str) -> PlannedItem:
    return PlannedItem(
        food_id=food.id,
        name=food.name,
        serving_size=food.serving_size,
        servings=round(servings, 2),
        role=role,
        calories=round(food.calories * servings, 1),
        protein_g=round(food.protein_g * servings, 1),
        carbs_g=round(food.carbs_g * servings, 1),
        fat_g=round(food.fat_g * servings, 1),
        fiber_g=round(food.fiber_g * servings, 1),
    )


def _candidates(pools: dict[str, list[FoodItem]], slot: MealSlot, role: str) -> list[FoodItem]:
    """Foods that can play `role` at this meal.

    The role's own source categories come first, falling back to the whole table when they cannot
    offer a real choice - without that fallback a vegan breakfast has no protein anchor at all,
    because the legumes and tofu that would serve as one are categorised for lunch and dinner.
    """
    eligible, _ = ROLE_RULES[role]
    sources = ROLE_SOURCES.get(role, (slot.key,))
    seen: set[int] = set()
    own = []
    for source in sources:
        for food in pools[source]:
            if food.id not in seen and eligible(food):
                seen.add(food.id)
                own.append(food)
    if len(own) >= MIN_ROLE_CANDIDATES:
        return own
    return [f for f in pools["all"] if eligible(f)]


def _pick(candidates: list[FoodItem], role: str, used: set[int], rng: random.Random,
          goal: str) -> FoodItem | None:
    """Choose a food for `role`, at random from the best-ranked few, skipping ones already used."""
    _, score = ROLE_RULES[role]
    fresh = [f for f in candidates if f.id not in used]
    pool = fresh or candidates  # a small table may force a repeat rather than an empty meal
    if not pool:
        return None
    if goal == "weight_management":  # prefer more fibre for the same energy
        ranked = sorted(pool, key=lambda f: (-score(f) - _fibre_score(f) / 20, f.name))
    else:
        ranked = sorted(pool, key=lambda f: (-score(f), f.name))
    return rng.choice(ranked[:VARIETY_POOL])


def _alternatives(candidates: list[FoodItem], chosen: FoodItem, target_calories: float,
                  rng: random.Random, limit: int = 3) -> list[Alternative]:
    """Same-role foods of a similar calorie size, offered as swaps."""
    others = [f for f in candidates if f.id != chosen.id]
    others.sort(key=lambda f: abs(f.calories * _round_servings(target_calories / _energy(f)) - target_calories))
    return [
        Alternative(
            food_id=f.id, name=f.name, serving_size=f.serving_size,
            servings=round(_round_servings(target_calories / _energy(f)), 2),
            calories=round(f.calories * _round_servings(target_calories / _energy(f))),
        )
        for f in others[:limit]
    ]


def _build_meal(slot: MealSlot, targets: MacroTargets, pools: dict[str, list[FoodItem]],
                used: set[int], rng: random.Random, goal: str) -> PlannedMeal:
    target_calories = targets.calories * slot.share
    target_protein = targets.protein_g * slot.share
    target_fat = targets.fat_g * slot.share
    items: list[PlannedItem] = []
    remaining = target_calories
    balancer = slot.roles[-1]

    for role in slot.roles:
        candidates = _candidates(pools, slot, role)
        food = _pick(candidates, role, used, rng, goal)
        if food is None:
            continue
        # On a small calorie target the half-serving minimum can be larger than the gap left. Add
        # the item only while doing so lands closer to the target than leaving it out, so smaller
        # plans simply get fewer items.
        if role != "protein" and remaining < _energy(food) * MIN_SERVINGS * 0.5:
            continue
        used.add(food.id)

        if role == balancer:
            # Close the remaining calorie gap.
            servings = _round_servings(remaining / _energy(food))
        elif role == "protein":
            # Size the anchor by protein, then cap it so it cannot swallow the whole meal.
            servings = _round_servings(target_protein * ANCHOR_PROTEIN_SHARE / max(food.protein_g, 0.1))
            cap = target_calories * ANCHOR_CALORIE_SHARE
            while servings > MIN_SERVINGS and food.calories * servings > cap:
                servings -= SERVING_STEP
        elif role == "fat":
            # Half the meal's fat comes from this item; the rest rides along with the other foods.
            servings = _round_servings(target_fat * 0.5 / max(food.fat_g, 0.1))
        else:
            servings = min(SIDE_MAX, max(SIDE_MIN, _round_servings(SIDE_CALORIES / _energy(food))))

        item = _scaled(food, servings, role)
        items.append(replace(item, alternatives=_alternatives(candidates, food, item.calories, rng)))
        remaining -= item.calories

    return PlannedMeal(
        key=slot.key,
        label=slot.label,
        target_calories=round(target_calories),
        items=items,
        calories=round(sum(i.calories for i in items), 1),
        protein_g=round(sum(i.protein_g for i in items), 1),
        carbs_g=round(sum(i.carbs_g for i in items), 1),
        fat_g=round(sum(i.fat_g for i in items), 1),
        fiber_g=round(sum(i.fiber_g for i in items), 1),
    )


def _build_day(day: date, targets: MacroTargets, pools: dict[str, list[FoodItem]], goal: str,
               seed: int) -> DayPlan:
    rng = random.Random(f"{seed}-{day.isoformat()}")
    used: set[int] = set()
    meals = [_build_meal(slot, targets, pools, used, rng, goal) for slot in MEAL_SLOTS]
    return DayPlan(
        date=day,
        meals=meals,
        calories=round(sum(m.calories for m in meals), 1),
        protein_g=round(sum(m.protein_g for m in meals), 1),
        carbs_g=round(sum(m.carbs_g for m in meals), 1),
        fat_g=round(sum(m.fat_g for m in meals), 1),
        fiber_g=round(sum(m.fiber_g for m in meals), 1),
    )


def build_plan(db: Session, profile: Profile, *, diet: str | None, exclude_allergens: list[str],
               start: date, days: int = 1) -> DietPlan:
    """Plan `days` consecutive days of meals for this profile, or explain why none can be planned."""
    body = assess_body(profile.age, profile.height_cm, profile.weight_kg, profile.health_flags or [])
    estimate = ns.estimate_calorie_range(
        profile.age, profile.sex, profile.height_cm, profile.weight_kg,
        profile.days_per_week, profile.goal, profile.health_flags or [],
    )  # fmt: skip
    filters = {"diet": diet, "exclude_allergens": sorted(exclude_allergens)}
    if estimate.calorie_min is None or estimate.calorie_max is None:
        # The same guard that withholds calorie numbers withholds the meal plan built on them.
        return DietPlan(False, estimate.explanation, body, None, [], [], filters, ns.DISCLAIMER)

    targets = macro_targets(estimate.calorie_min, estimate.calorie_max, profile.weight_kg, profile.goal)

    by_category: dict[str, list[FoodItem]] = {}
    for category in ("breakfast", "lunch", "dinner", "snack"):
        _, items = ns.filter_foods(
            db, diet=diet, exclude_allergens=exclude_allergens, meal_category=category,
            max_calories=None, min_protein_g=None, query=None, limit=1000, offset=0,
        )  # fmt: skip
        by_category[category] = [f for f in items if not INGREDIENT_ONLY.search(f.name)]
    # Lunch and dinner foods are interchangeable in practice, so each main meal draws on both.
    mains = by_category["lunch"] + by_category["dinner"]
    pools = {
        "breakfast": by_category["breakfast"],
        "lunch": mains,
        "dinner": mains,
        "snack": by_category["snack"],
        "all": by_category["breakfast"] + mains + by_category["snack"],
    }
    if not any(pools[s.key] for s in MEAL_SLOTS):
        return DietPlan(
            False, "No foods match your dietary preferences and allergy exclusions, so a plan cannot be built.",
            body, targets, [], [], filters, ns.DISCLAIMER,
        )

    plans = [
        _build_day(date.fromordinal(start.toordinal() + offset), targets, pools, profile.goal, profile.user_id)
        for offset in range(days)
    ]
    return DietPlan(
        available=True,
        reason=None,
        body=body,
        targets=targets,
        days=plans,
        tips=list(ns.MEAL_GUIDANCE.get(profile.goal, ns.MEAL_GUIDANCE["general_fitness"])),
        applied_filters=filters,
        disclaimer=ns.DISCLAIMER,
    )
