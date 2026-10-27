# Nutrition data (`foods.csv`)

## Source

**USDA, Agricultural Research Service. FoodData Central: SR Legacy, April 2018 release.**
https://fdc.nal.usda.gov/ · download: `FoodData_Central_sr_legacy_food_csv_2018-04.zip` (6.1 MB)
FoodData Central data are in the public domain (CC0 1.0).

SR Legacy is the final release of USDA's Standard Reference database and remains the standard
reference for generic foods. It does not cover Indian prepared dishes such as dal, paneer or idli,
so the table includes their base ingredients instead (lentils, pigeon peas, mung beans, chickpea
flour, ghee, chapati, naan).

## How the table is built

`foods.csv` holds 299 foods and is built in two passes. The first 147 are curated by hand and are
authoritative; the remaining 152 are an automated expansion that adds variety for the diet planner
and never touches the curated rows.

### Pass 1 - the curated 147 (`backend/scripts/build_foods_from_usda.py`)

1. Each food in the curated list is looked up by its exact USDA description, and its FDC ID is recorded.
2. Energy (nutrient 1008, kcal), protein (1003), carbohydrate by difference (1005), total fat (1004)
   and total dietary fibre (1079) are read per 100 g from `food_nutrient.csv`.
3. A USDA household portion from `food_portion.csv` (e.g. `1 cup (198 g)`, `1 large (50 g)`) is used
   as the serving, and nutrients are scaled to it. Meat and fish use 100 g when no single-serving
   portion is listed.
4. USDA has no fibre value for cooked shrimp or tempeh; those are recorded as 0.

To rebuild after editing the selection:

```bash
python backend/scripts/build_foods_from_usda.py --usda-dir data_sources/usda/FoodData_Central_sr_legacy_food_csv_2018-04
```

### Pass 2 - the expansion (`backend/scripts/expand_foods_from_usda.py`)

Run after pass 1, over the file pass 1 produced. For each name on a list of common foods it searches
SR Legacy and keeps the plainest preparation available, ranked: cooked without salt, then cooked,
then raw. Battered, fried, salted, sweetened, branded, infant and organ-meat entries are rejected
outright. Labels come from keyword rules over the USDA description rather than by hand, so they are
deliberately cautious - a food keeps an allergen unless it is clearly free of it, and nothing
processed is marked gluten-free.

Portions are chosen per food category and then capped: oils and spices are measured in spoons, nuts
in ounces, and any portion over 400 kcal is re-measured, because `1 cup` of sesame oil is a genuine
USDA portion but not a serving anyone eats.

```bash
python backend/scripts/expand_foods_from_usda.py --usda-dir data_sources/usda/FoodData_Central_sr_legacy_food_csv_2018-04
```

Re-running it is safe: rows already in the file are matched by FDC ID and name and are left alone.

The API reloads the `food_items` table on startup whenever `foods.csv` has changed.

## What the diet planner does not use

`backend/app/services/diet_planner.py` skips foods that are cooking ingredients rather than servings
(flour, dry semolina, wheat gluten, yeast). They stay in the table because looking up the energy in
100 g of flour is useful in the food explorer, but "1 cup of dry semolina" is not a meal.

## Columns

| column | origin |
|---|---|
| food_id | row number |
| food_name | short display name (FitAI) |
| serving_size, serving_grams | USDA household portion |
| calories, protein_g, carbohydrates_g, fat_g, fiber_g | USDA, scaled to the serving |
| allergens | **assigned by FitAI**: milk, egg, fish, shellfish, tree_nuts, peanuts, wheat, soy, sesame |
| dietary_tags | **assigned by FitAI**: vegan, vegetarian, gluten_free |
| meal_category | **assigned by FitAI**: breakfast, lunch, dinner, snack |
| fdc_id, usda_description, source | USDA traceability |

**Important:** USDA SR Legacy does not provide allergen or diet labels. FitAI's labels are editorial
and conservative. For example, oat and processed products are not marked gluten-free because of possible
cross-contact. They are meant for filtering suggestions, not as allergy-safety guarantees.

## Citation for the report

> U.S. Department of Agriculture, Agricultural Research Service. FoodData Central: SR Legacy
> (April 2018). Available from https://fdc.nal.usda.gov/. Accessed 2026-09-17.
