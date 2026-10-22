"""Build backend/app/data/foods.csv from the USDA FoodData Central SR Legacy CSV release.

Source: USDA, Agricultural Research Service. FoodData Central, SR Legacy (April 2018).
        https://fdc.nal.usda.gov/  (public domain / CC0)
Download: https://fdc.nal.usda.gov/fdc-datasets/FoodData_Central_sr_legacy_food_csv_2018-04.zip

Usage (from the repository root, after extracting the zip):
    python backend/scripts/build_foods_from_usda.py \
        --usda-dir data_sources/usda/FoodData_Central_sr_legacy_food_csv_2018-04

What comes from USDA:   food description, FDC ID, energy, protein, carbohydrate, fat, fibre
                        (per 100 g), and the household portion used as the serving size.
What FitAI assigns:     short display name, meal category, dietary tags (vegan, vegetarian,
                        gluten_free) and allergens. USDA SR Legacy does not provide these;
                        they are editorial labels for filtering and must not be treated as
                        allergen-safety guarantees.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from fractions import Fraction
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "app" / "data" / "foods.csv"

NUTRIENTS = {"calories": "1008", "protein_g": "1003", "fat_g": "1004", "carbohydrates_g": "1005", "fiber_g": "1079"}
ENERGY_FALLBACKS = ("2048", "2047")  # Atwater specific / general factors, used only if 1008 is missing

# diet: "vegan" (also vegetarian), "veg" (vegetarian), "-" (neither)
# gf: whole/unprocessed foods naturally free of gluten grains; processed and oat products are conservatively False
# portion: regex matched against the USDA portion modifier; None or no match -> 100 g
# (USDA description prefix, display name, meal category, portion regex, diet, gf, allergens)
SELECTION: list[tuple[str, str, str, str | None, str, bool, str]] = [
    # ---- Breakfast: grains, dairy, eggs ----------------------------------------------------------------
    ("Cereals, oats, regular and quick, not fortified, dry", "Rolled oats (dry)", "breakfast", r"^cup$", "vegan", False, ""),
    ("Cereals, oats, regular and quick, unenriched, cooked with water (includes boiling and microwaving), without salt", "Oatmeal, cooked with water", "breakfast", r"^cup", "vegan", False, ""),
    ("Cereals ready-to-eat, granola, homemade", "Granola, homemade", "breakfast", r"^cup", "veg", False, "tree_nuts"),
    ("Buckwheat groats, roasted, cooked", "Buckwheat groats, cooked", "breakfast", r"^cup", "vegan", True, ""),
    ("Bread, whole-wheat, commercially prepared", "Whole-wheat bread", "breakfast", r"^slice", "vegan", False, "wheat"),
    ("Bread, multi-grain (includes whole-grain)", "Multi-grain bread", "breakfast", r"^slice", "vegan", False, "wheat"),
    ("Bread, white, commercially prepared (includes soft bread crumbs)", "White bread", "breakfast", r"^slice", "vegan", False, "wheat"),
    ("Yogurt, Greek, plain, nonfat", "Greek yogurt, plain, nonfat", "breakfast", r"container|cup", "veg", True, "milk"),
    ("Yogurt, Greek, plain, lowfat", "Greek yogurt, plain, low-fat", "breakfast", r"container|cup", "veg", True, "milk"),
    ("Yogurt, plain, low fat", "Yogurt (curd), plain, low-fat", "breakfast", r"^cup|container", "veg", True, "milk"),
    ("Milk, lowfat, fluid, 1% milkfat, with added vitamin A and vitamin D", "Milk, low-fat 1%", "breakfast", r"^cup", "veg", True, "milk"),
    ("Milk, whole, 3.25% milkfat, with added vitamin D", "Milk, whole", "breakfast", r"^cup", "veg", True, "milk"),
    ("Soymilk, original and vanilla, with added calcium, vitamins A and D", "Soy milk, calcium-fortified", "breakfast", r"^cup", "vegan", True, "soy"),
    ("Beverages, almond milk, unsweetened, shelf stable", "Almond milk, unsweetened", "breakfast", r"^cup", "vegan", True, "tree_nuts"),
    ("Egg, whole, cooked, hard-boiled", "Egg, hard-boiled", "breakfast", r"^large", "veg", True, "egg"),
    ("Egg, whole, cooked, scrambled", "Egg, scrambled", "breakfast", r"^large", "veg", True, "egg|milk"),
    ("Egg, whole, cooked, poached", "Egg, poached", "breakfast", r"^large", "veg", True, "egg"),
    ("Egg, white, raw, fresh", "Egg white", "breakfast", r"^large", "veg", True, "egg"),
    ("Seeds, chia seeds, dried", "Chia seeds", "breakfast", r"^oz", "vegan", True, ""),
    ("Seeds, flaxseed", "Flaxseeds", "breakfast", r"^tbsp, whole|^tbsp", "vegan", True, ""),
    ("Honey", "Honey", "breakfast", r"^tbsp", "veg", True, ""),
    ("Jams and preserves", "Jam", "breakfast", r"^tbsp", "vegan", True, ""),
    ("Beverages, coffee, brewed, prepared with tap water", "Coffee, black", "breakfast", r"^cup", "vegan", True, ""),
    ("Beverages, tea, black, brewed, prepared with tap water", "Tea, black, unsweetened", "breakfast", r"^cup", "vegan", True, ""),
    ("Orange juice, raw", "Orange juice, fresh", "breakfast", r"^cup", "vegan", True, ""),
    ("Cereals, corn grits, white, regular and quick, enriched, cooked with water, without salt", "Corn grits, cooked", "breakfast", r"^cup", "vegan", True, ""),
    ("Semolina, enriched", "Semolina (sooji), dry", "breakfast", r"^cup", "vegan", False, "wheat"),
    # ---- Fruit -------------------------------------------------------------------------------------------
    ("Bananas, raw", "Banana", "snack", r"^medium", "vegan", True, ""),
    ("Apples, raw, with skin", "Apple, with skin", "snack", r"^medium", "vegan", True, ""),
    ("Oranges, raw, all commercial varieties", "Orange", "snack", r"^large|^fruit", "vegan", True, ""),
    ("Blueberries, raw", "Blueberries", "breakfast", r"^cup", "vegan", True, ""),
    ("Strawberries, raw", "Strawberries", "breakfast", r"^cup, halves|^cup", "vegan", True, ""),
    ("Raspberries, raw", "Raspberries", "snack", r"^cup", "vegan", True, ""),
    ("Grapes, red or green (European type, such as Thompson seedless), raw", "Grapes", "snack", r"^cup", "vegan", True, ""),
    ("Mangos, raw", "Mango", "snack", r"^cup, pieces|^cup", "vegan", True, ""),
    ("Papayas, raw", "Papaya", "breakfast", r"^cup, 1\" pieces|^cup", "vegan", True, ""),
    ("Pineapple, raw, all varieties", "Pineapple", "snack", r"^cup, chunks|^cup", "vegan", True, ""),
    ("Watermelon, raw", "Watermelon", "snack", r"^cup, diced|^cup", "vegan", True, ""),
    ("Melons, cantaloupe, raw", "Cantaloupe", "snack", r"^cup, cubes|^cup", "vegan", True, ""),
    ("Guavas, common, raw", "Guava", "snack", r"^fruit", "vegan", True, ""),
    ("Pomegranates, raw", "Pomegranate arils", "snack", r"^cup arils|^cup", "vegan", True, ""),
    ("Pears, raw", "Pear", "snack", r"^medium", "vegan", True, ""),
    ("Kiwifruit, green, raw", "Kiwi fruit", "snack", r"^fruit", "vegan", True, ""),
    ("Peaches, yellow, raw", "Peach", "snack", r"^medium", "vegan", True, ""),
    ("Cherries, sweet, raw", "Cherries, sweet", "snack", r"^cup, with pits|^cup", "vegan", True, ""),
    ("Dates, medjool", "Dates, medjool", "snack", r"^date", "vegan", True, ""),
    ("Raisins, dark, seedless", "Raisins", "snack", r"^small box|^oz|^cup", "vegan", True, ""),
    ("Figs, dried, uncooked", "Figs, dried", "snack", r"^fig", "vegan", True, ""),
    ("Avocados, raw, all commercial varieties", "Avocado", "lunch", r"^cup, sliced|^cup", "vegan", True, ""),
    ("Nuts, coconut water (liquid from coconuts)", "Coconut water", "snack", r"^cup", "vegan", True, ""),
    # ---- Nuts, seeds, snacks -------------------------------------------------------------------------------
    ("Nuts, almonds", "Almonds", "snack", r"^oz", "vegan", True, "tree_nuts"),
    ("Nuts, walnuts, english", "Walnuts", "snack", r"^oz", "vegan", True, "tree_nuts"),
    ("Nuts, cashew nuts, raw", "Cashews", "snack", r"^oz", "vegan", True, "tree_nuts"),
    ("Nuts, pistachio nuts, dry roasted, without salt added", "Pistachios, unsalted", "snack", r"^oz", "vegan", True, "tree_nuts"),
    ("Peanuts, all types, dry-roasted, without salt", "Peanuts, dry-roasted, unsalted", "snack", r"^oz", "vegan", True, "peanuts"),
    ("Peanut butter, smooth style, without salt", "Peanut butter, unsalted", "snack", r"^tbsp|tablespoon", "vegan", True, "peanuts"),
    ("Seeds, sunflower seed kernels, dry roasted, without salt", "Sunflower seeds, unsalted", "snack", r"^oz", "vegan", True, ""),
    ("Seeds, pumpkin and squash seed kernels, dried", "Pumpkin seeds", "snack", r"^oz", "vegan", True, ""),
    ("Seeds, sesame seeds, whole, dried", "Sesame seeds", "snack", r"^tbsp", "vegan", True, "sesame"),
    ("Snacks, popcorn, air-popped", "Popcorn, air-popped", "snack", r"^cup", "vegan", True, ""),
    ("Snacks, rice cakes, brown rice, plain", "Rice cakes, brown rice", "snack", r"^cake", "vegan", True, ""),
    ("Crackers, whole-wheat", "Whole-wheat crackers", "snack", r"^cracker|^serving|^oz", "vegan", False, "wheat"),
    ("Chocolate, dark, 70-85% cacao solids", "Dark chocolate, 70-85%", "snack", r"^oz", "veg", False, "milk|soy"),
    ("Hummus, commercial", "Hummus", "snack", r"^tbsp", "vegan", False, "sesame"),
    ("Beverages, Whey protein powder isolate", "Whey protein isolate powder", "snack", r"scoop", "veg", False, "milk"),
    ("Cheese, cottage, lowfat, 1% milkfat", "Cottage cheese, low-fat", "snack", r"^cup|^4 oz|container", "veg", True, "milk"),
    ("Cheese, cheddar", "Cheddar cheese", "snack", r"^oz|^slice", "veg", True, "milk"),
    ("Cheese, mozzarella, part skim milk", "Mozzarella, part-skim", "snack", r"^oz", "veg", True, "milk"),
    ("Cheese, ricotta, part skim milk", "Ricotta, part-skim", "snack", r"^cup", "veg", True, "milk"),
    ("Kefir, lowfat, plain, LIFEWAY", "Kefir, low-fat, plain", "snack", r"^cup", "veg", True, "milk"),
    ("Carrots, raw", "Carrot", "snack", r"^medium", "vegan", True, ""),
    ("Cucumber, with peel, raw", "Cucumber", "snack", r"^cup, sliced|^cup", "vegan", True, ""),
    # ---- Proteins ---------------------------------------------------------------------------------------------
    ("Chicken, broilers or fryers, breast, meat only, cooked, roasted", "Chicken breast, roasted, skinless", "lunch", None, "-", True, ""),
    ("Chicken, broilers or fryers, thigh, meat only, cooked, roasted", "Chicken thigh, roasted, skinless", "dinner", None, "-", True, ""),
    ("Turkey, whole, breast, meat only, cooked, roasted", "Turkey breast, roasted", "lunch", None, "-", True, ""),
    ("Fish, salmon, Atlantic, farmed, cooked, dry heat", "Salmon, baked", "dinner", None, "-", True, "fish"),
    ("Fish, tuna, light, canned in water, drained solids", "Tuna, canned in water", "lunch", None, "-", True, "fish"),
    ("Fish, tilapia, cooked, dry heat", "Tilapia, baked", "dinner", None, "-", True, "fish"),
    ("Fish, cod, Atlantic, cooked, dry heat", "Cod, baked", "dinner", None, "-", True, "fish"),
    ("Fish, mackerel, Atlantic, cooked, dry heat", "Mackerel, baked", "dinner", None, "-", True, "fish"),
    ("Fish, sardine, Atlantic, canned in oil, drained solids with bone", "Sardines, canned in oil", "lunch", r"^can", "-", True, "fish"),
    ("Crustaceans, shrimp, cooked", "Shrimp, cooked", "dinner", r"^oz", "-", True, "shellfish"),
    ("Beef, ground, 90% lean meat / 10% fat, patty, cooked, broiled", "Lean beef mince 90/10, cooked", "dinner", None, "-", True, ""),
    ("Pork, fresh, loin, tenderloin, separable lean only, cooked, roasted", "Pork tenderloin, roasted", "dinner", None, "-", True, ""),
    ("Lamb, ground, cooked, broiled", "Lamb mince, cooked", "dinner", None, "-", True, ""),
    ("Tofu, raw, firm, prepared with calcium sulfate", "Tofu, firm", "dinner", r"^cup", "vegan", True, "soy"),
    ("Tempeh", "Tempeh", "dinner", r"^cup", "vegan", True, "soy"),
    ("Edamame, frozen, prepared", "Edamame, cooked", "snack", r"^cup", "vegan", True, "soy"),
    ("Soybeans, mature cooked, boiled, without salt", "Soybeans, cooked", "dinner", r"^cup", "vegan", True, "soy"),
    # ---- Legumes (bases for dal, chana, rajma) -----------------------------------------------------------------
    ("Lentils, mature seeds, cooked, boiled, without salt", "Lentils, cooked (dal base)", "lunch", r"^cup", "vegan", True, ""),
    ("Lentils, pink or red, raw", "Red lentils (masoor), dry", "lunch", r"^cup", "vegan", True, ""),
    ("Pigeon peas (red gram), mature seeds, cooked, boiled, without salt", "Pigeon peas (toor), cooked", "lunch", r"^cup", "vegan", True, ""),
    ("Chickpeas (garbanzo beans, bengal gram), mature seeds, cooked, boiled, without salt", "Chickpeas (chana), cooked", "lunch", r"^cup", "vegan", True, ""),
    ("Beans, kidney, red, mature seeds, cooked, boiled, without salt", "Kidney beans (rajma), cooked", "lunch", r"^cup", "vegan", True, ""),
    ("Mung beans, mature seeds, cooked, boiled, without salt", "Mung beans (moong), cooked", "lunch", r"^cup", "vegan", True, ""),
    ("Mung beans, mature seeds, sprouted, raw", "Mung bean sprouts", "snack", r"^cup", "vegan", True, ""),
    ("Beans, black, mature seeds, cooked, boiled, without salt", "Black beans, cooked", "lunch", r"^cup", "vegan", True, ""),
    ("Beans, pinto, mature seeds, cooked, boiled, without salt", "Pinto beans, cooked", "dinner", r"^cup", "vegan", True, ""),
    ("Cowpeas, common (blackeyes, crowder, southern), mature seeds, cooked, boiled, without salt", "Black-eyed peas (lobia), cooked", "lunch", r"^cup", "vegan", True, ""),
    ("Peas, split, mature seeds, cooked, boiled, without salt", "Split peas, cooked", "dinner", r"^cup", "vegan", True, ""),
    ("Chickpea flour (besan)", "Chickpea flour (besan)", "lunch", r"^cup", "vegan", True, ""),
    # ---- Grains and starches -------------------------------------------------------------------------------
    ("Rice, brown, long-grain, cooked", "Brown rice, cooked", "lunch", r"^cup", "vegan", True, ""),
    ("Rice, white, long-grain, regular, enriched, cooked", "White rice, cooked", "lunch", r"^cup", "vegan", True, ""),
    ("Quinoa, cooked", "Quinoa, cooked", "lunch", r"^cup", "vegan", True, ""),
    ("Millet, cooked", "Millet, cooked", "lunch", r"^cup", "vegan", True, ""),
    ("Barley, pearled, cooked", "Barley, cooked", "dinner", r"^cup", "vegan", False, ""),
    ("Bulgur, cooked", "Bulgur, cooked", "dinner", r"^cup", "vegan", False, "wheat"),
    ("Couscous, cooked", "Couscous, cooked", "dinner", r"^cup", "vegan", False, "wheat"),
    ("Pasta, whole-wheat, cooked", "Whole-wheat pasta, cooked", "dinner", r"^cup", "vegan", False, "wheat"),
    ("Pasta, cooked, enriched, without added salt", "Pasta, cooked", "dinner", r"^cup", "vegan", False, "wheat"),
    ("Bread, chapati or roti, whole wheat, commercially prepared, frozen", "Chapati / roti, whole wheat", "dinner", r"^piece", "vegan", False, "wheat"),
    ("Bread, naan, whole wheat, commercially prepared, refrigerated", "Naan, whole wheat", "dinner", r"^piece", "veg", False, "wheat|milk"),
    ("Bread, pita, whole-wheat", "Whole-wheat pita", "lunch", r"^pita, small|^pita", "vegan", False, "wheat"),
    ("Tortillas, ready-to-bake or -fry, corn, without added salt", "Corn tortilla", "lunch", r"^tortilla", "vegan", True, ""),
    ("Wheat flour, whole-grain", "Whole-wheat flour (atta)", "dinner", r"^cup", "vegan", False, "wheat"),
    ("Sweet potato, cooked, baked in skin, flesh, without salt", "Sweet potato, baked", "dinner", r"^medium", "vegan", True, ""),
    ("Potatoes, baked, flesh and skin, without salt", "Potato, baked with skin", "dinner", r"^potato medium", "vegan", True, ""),
    ("Corn, sweet, yellow, frozen, kernels cut off cob, boiled, drained, without salt", "Sweet corn, cooked", "dinner", r"^cup", "vegan", True, ""),
    # ---- Vegetables ----------------------------------------------------------------------------------------------
    ("Broccoli, cooked, boiled, drained, without salt", "Broccoli, cooked", "dinner", r"^cup", "vegan", True, ""),
    ("Spinach, raw", "Spinach, raw", "lunch", r"^cup", "vegan", True, ""),
    ("Spinach, cooked, boiled, drained, without salt", "Spinach, cooked", "dinner", r"^cup", "vegan", True, ""),
    ("Kale, raw", "Kale, raw", "lunch", r"^cup", "vegan", True, ""),
    ("Tomatoes, red, ripe, raw, year round average", "Tomato", "lunch", r"^medium", "vegan", True, ""),
    ("Lettuce, cos or romaine, raw", "Romaine lettuce", "lunch", r"^cup shredded|^cup", "vegan", True, ""),
    ("Peppers, sweet, red, raw", "Red bell pepper", "lunch", r"^cup, chopped|^cup", "vegan", True, ""),
    ("Cauliflower, cooked, boiled, drained, without salt", "Cauliflower, cooked", "dinner", r"^cup", "vegan", True, ""),
    ("Cabbage, raw", "Cabbage, raw", "lunch", r"^cup, chopped|^cup", "vegan", True, ""),
    ("Onions, raw", "Onion", "dinner", r"^cup, chopped|^medium", "vegan", True, ""),
    ("Mushrooms, white, raw", "Mushrooms, white", "dinner", r"^cup, pieces|^cup", "vegan", True, ""),
    ("Beans, snap, green, cooked, boiled, drained, without salt", "Green beans, cooked", "dinner", r"^cup", "vegan", True, ""),
    ("Peas, green, frozen, cooked, boiled, drained, without salt", "Green peas, cooked", "dinner", r"^cup", "vegan", True, ""),
    ("Squash, summer, zucchini, includes skin, cooked, boiled, drained, without salt", "Zucchini, cooked", "dinner", r"^cup", "vegan", True, ""),
    ("Okra, cooked, boiled, drained, without salt", "Okra (bhindi), cooked", "dinner", r"^cup", "vegan", True, ""),
    ("Eggplant, cooked, boiled, drained, without salt", "Eggplant (brinjal), cooked", "dinner", r"^cup", "vegan", True, ""),
    ("Balsam-pear (bitter gourd), pods, cooked, boiled, drained, without salt", "Bitter gourd (karela), cooked", "dinner", r"^cup", "vegan", True, ""),
    ("Pumpkin, cooked, boiled, drained, without salt", "Pumpkin, cooked", "dinner", r"^cup", "vegan", True, ""),
    ("Beets, cooked, boiled, drained", "Beetroot, cooked", "lunch", r"^cup|^beet", "vegan", True, ""),
    ("Asparagus, cooked, boiled, drained", "Asparagus, cooked", "dinner", r"^cup", "vegan", True, ""),
    ("Brussels sprouts, cooked, boiled, drained, without salt", "Brussels sprouts, cooked", "dinner", r"^cup", "vegan", True, ""),
    ("Garlic, raw", "Garlic", "dinner", r"^clove", "vegan", True, ""),
    # ---- Fats, soups, sauces ---------------------------------------------------------------------------------------
    ("Oil, olive, salad or cooking", "Olive oil", "dinner", r"^tablespoon|^tbsp", "vegan", True, ""),
    ("Oil, canola", "Canola oil", "dinner", r"^tablespoon|^tbsp", "vegan", True, ""),
    ("Oil, coconut", "Coconut oil", "dinner", r"^tablespoon|^tbsp", "vegan", True, ""),
    ("Butter, without salt", "Butter, unsalted", "breakfast", r"^tbsp", "veg", True, "milk"),
    ("Butter, Clarified butter (ghee)", "Ghee (clarified butter)", "dinner", None, "veg", True, "milk"),
    ("Sauce, pasta, spaghetti/marinara, ready-to-serve", "Marinara sauce", "dinner", r"^serving", "vegan", False, ""),
    ("Soup, chicken noodle, canned, prepared with equal volume water", "Chicken noodle soup, canned", "lunch", r"^serving", "-", False, "wheat|egg"),
]

FRACTIONS = {0.25: "1/4", 0.33: "1/3", 0.5: "1/2", 0.67: "2/3", 0.75: "3/4"}


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def resolve(foods: list[dict], prefix: str) -> dict:
    exact = [f for f in foods if f["description"] == prefix]
    if len(exact) == 1:
        return exact[0]
    starts = [f for f in foods if f["description"].startswith(prefix)]
    # Prefer the entry whose remainder is only USDA's "(Includes foods for ...)" note.
    note = [f for f in starts if re.fullmatch(r"\s*\(Includes foods for USDA's Food Distribution Program\)", f["description"][len(prefix):])]
    if len(note) == 1:
        return note[0]
    if len(starts) == 1:
        return starts[0]
    raise LookupError(f"{len(starts)} matches for {prefix!r}: " + "; ".join(f["description"] for f in starts[:5]))


def fmt_amount(amount: float) -> str:
    if amount in FRACTIONS:
        return FRACTIONS[amount]
    return str(Fraction(amount).limit_denominator(8)) if amount != int(amount) else str(int(amount))


def choose_portion(portions: list[dict], pattern: str | None) -> tuple[str, float]:
    if pattern:
        rx = re.compile(pattern, re.IGNORECASE)
        for p in sorted(portions, key=lambda p: int(p["seq_num"] or 0)):
            modifier = (p["modifier"] or p["portion_description"]).strip()
            grams = float(p["gram_weight"] or 0)
            amount = float(p["amount"] or 1)
            if rx.search(modifier) and grams > 0:
                if amount > 1 and not re.match(r"(oz|fl oz)\b", modifier, re.IGNORECASE):  # "3 scoop" -> "1 scoop"; keep "3 oz"
                    grams, amount = grams / amount, 1.0
                return f"{fmt_amount(amount)} {modifier} ({grams:.0f} g)", grams
    return "100 g", 100.0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--usda-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()

    foods = [f for f in read_csv(args.usda_dir / "food.csv") if f["data_type"] == "sr_legacy_food"]
    selected, errors = [], []
    for entry in SELECTION:
        try:
            selected.append((resolve(foods, entry[0]), entry))
        except LookupError as exc:
            errors.append(str(exc))
    if errors:
        sys.exit("Unresolved foods:\n  " + "\n  ".join(errors))

    ids = {f["fdc_id"] for f, _ in selected}
    if len(ids) != len(selected):
        sys.exit("duplicate FDC IDs in selection")
    wanted = set(NUTRIENTS.values()) | set(ENERGY_FALLBACKS)
    nutrients: dict[str, dict[str, float]] = {}
    with (args.usda_dir / "food_nutrient.csv").open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["fdc_id"] in ids and row["nutrient_id"] in wanted and row["amount"]:
                nutrients.setdefault(row["fdc_id"], {})[row["nutrient_id"]] = float(row["amount"])
    portions: dict[str, list[dict]] = {}
    for row in read_csv(args.usda_dir / "food_portion.csv"):
        if row["fdc_id"] in ids:
            portions.setdefault(row["fdc_id"], []).append(row)

    rows, warnings = [], []
    for i, (food, (_, name, meal, pattern, diet, gf, allergens)) in enumerate(selected, start=1):
        per100 = nutrients.get(food["fdc_id"], {})
        if NUTRIENTS["calories"] not in per100:
            fallback = next((per100[k] for k in ENERGY_FALLBACKS if k in per100), None)
            if fallback is None:
                sys.exit(f"no energy value for {food['description']}")
            per100[NUTRIENTS["calories"]] = fallback
        for key in ("protein_g", "fat_g", "carbohydrates_g"):
            if NUTRIENTS[key] not in per100:
                sys.exit(f"missing {key} for {food['description']}")
        if NUTRIENTS["fiber_g"] not in per100:
            warnings.append(f"no fibre value (recorded as 0): {food['description']}")
        serving, grams = choose_portion(portions.get(food["fdc_id"], []), pattern)
        if pattern and serving == "100 g":
            warnings.append(f"portion {pattern!r} not found, used 100 g: {food['description']}")
        scale = grams / 100.0
        tags = ["vegan", "vegetarian"] if diet == "vegan" else ["vegetarian"] if diet == "veg" else []
        if gf:
            tags.append("gluten_free")
        rows.append({
            "food_id": i,
            "food_name": name,
            "serving_size": serving,
            "calories": round(per100[NUTRIENTS["calories"]] * scale),
            "protein_g": round(per100[NUTRIENTS["protein_g"]] * scale, 1),
            "carbohydrates_g": round(per100[NUTRIENTS["carbohydrates_g"]] * scale, 1),
            "fat_g": round(per100[NUTRIENTS["fat_g"]] * scale, 1),
            "fiber_g": round(per100.get(NUTRIENTS["fiber_g"], 0.0) * scale, 1),
            "allergens": allergens,
            "dietary_tags": "|".join(tags),
            "meal_category": meal,
            "serving_grams": round(grams, 1),
            "fdc_id": food["fdc_id"],
            "usda_description": food["description"],
            "source": "USDA FoodData Central SR Legacy 2018-04",
        })  # fmt: skip

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    for w in warnings:
        print("warning:", w)
    print(f"wrote {len(rows)} foods to {args.out}")


if __name__ == "__main__":
    main()
