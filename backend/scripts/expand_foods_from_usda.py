"""Expand `foods.csv` with more USDA SR Legacy foods, so meal plans have variety.

`build_foods_from_usda.py` hand-picks ~150 foods and hand-labels every field. Curating several
hundred that way is impractical, so this script works from a list of common food names: for each
name it searches SR Legacy, prefers the plainest preparation (cooked without salt, else raw, never
battered/fried/branded), and derives the labels from keywords. Every hand-curated row is copied
through untouched — those stay authoritative.

Selecting by name rather than by "whatever USDA lists first" matters: SR Legacy contains hundreds of
foods nobody plans a meal around (eppaw, cardoon, lambsquarters), and they crowd out the staples.

The labels this script assigns (meal category, vegan/vegetarian/gluten-free, allergens) are
editorial, as in the curated file, and deliberately conservative: anything not clearly free of an
allergen keeps the allergen, and anything processed is not marked gluten-free.

Usage (from the repository root):
    python backend/scripts/expand_foods_from_usda.py \
        --usda-dir data_sources/usda/FoodData_Central_sr_legacy_food_csv_2018-04
"""

from __future__ import annotations

import argparse
import collections
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.build_foods_from_usda import (  # noqa: E402
    ENERGY_FALLBACKS, NUTRIENTS, OUT, choose_portion, read_csv,
)

# Common foods to look for, grouped by the meal FitAI will suggest them in. Each entry is the start
# of a USDA description; the best-ranked match is taken. A trailing "*N" asks for N distinct matches
# (e.g. "Bread*3" picks three breads), which is how one term covers a family of foods.
WANTED: dict[str, list[str]] = {
    "breakfast": [
        "Egg, whole, cooked, hard-boiled", "Egg, whole, cooked, scrambled", "Egg, whole, cooked, poached",
        "Egg, white, raw", "Egg, yolk, raw", "Egg substitute, liquid",
        "Milk, whole", "Milk, lowfat, fluid, 1%", "Milk, nonfat, fluid", "Milk, buttermilk, fluid",
        "Yogurt, plain, low fat", "Yogurt, plain, whole milk", "Yogurt, Greek, plain, nonfat",
        "Yogurt, Greek, plain, lowfat", "Cheese, cottage, lowfat, 2%", "Cheese, cottage, creamed",
        "Cheese, cheddar", "Cheese, mozzarella, part skim milk", "Cheese, feta", "Cheese, parmesan, grated",
        "Cheese, ricotta, part skim milk", "Cheese, swiss", "Cheese, cream", "Cream, sour, cultured",
        "Cereals, oats, regular and quick", "Cereals ready-to-eat, granola", "Cereals, corn grits",
        "Cereals, farina", "Cereals, oat bran", "Cereals, cream of wheat",
        "Bread, whole-wheat", "Bread, white", "Bread, rye", "Bread, pita, whole-wheat", "Bread, raisin",
        "Bagels, plain", "English muffins, plain", "Muffins, oat bran", "Pancakes, plain",
        "Waffle, plain", "Tortillas, ready-to-bake or -fry, corn",
    ],
    "lunch": [
        "Chicken, broilers or fryers, breast, meat only, cooked, roasted",
        "Chicken, broilers or fryers, thigh, meat only, cooked, roasted",
        "Chicken, broilers or fryers, drumstick, meat only, cooked",
        "Turkey, whole, breast, meat only, cooked, roasted", "Turkey, ground, cooked",
        "Turkey breast, low salt", "Duck, domesticated, meat only, cooked, roasted",
        "Lentils, mature seeds, cooked", "Lentils, sprouted, raw",
        "Chickpeas (garbanzo beans, bengal gram), mature seeds, cooked",
        "Beans, black, mature seeds, cooked", "Beans, kidney, red, mature seeds, cooked",
        "Beans, pinto, mature seeds, cooked", "Beans, navy, mature seeds, cooked",
        "Beans, white, mature seeds, cooked", "Beans, great northern, mature seeds, cooked",
        "Beans, adzuki, mature seeds, cooked", "Mung beans, mature seeds, cooked",
        "Lima beans, immature seeds, cooked, boiled", "Beans, cranberry (roman), mature seeds, cooked",
        "Peas, split, mature seeds, cooked", "Cowpeas, common (blackeyes, crowder, southern), mature seeds, cooked",
        "Soybeans, mature seeds, cooked", "Soybeans, mature cooked",
        "Tofu, firm, prepared with calcium sulfate", "Tofu, raw, regular", "Tofu, extra firm",
        "Tempeh", "Natto", "Miso", "Soymilk",
        "Hummus, home prepared", "Falafel, home-prepared", "Peanut butter, smooth style",
        "Rice, brown, long-grain, cooked", "Rice, brown, medium-grain, cooked",
        "Rice, white, long-grain, regular, enriched, cooked", "Wild rice, cooked",
        "Quinoa, cooked", "Buckwheat groats, roasted, cooked", "Bulgur, cooked",
        "Couscous, cooked", "Barley, pearled, cooked", "Millet, cooked", "Amaranth grain, cooked",
        "Sorghum grain", "Teff, cooked", "Spelt, cooked",
        "Pasta, whole-wheat, cooked", "Noodles, egg, cooked, enriched", "Rice noodles, cooked",
        "Cornmeal, whole-grain, yellow", "Wheat flour, whole-grain",
        "Chickpea flour (besan)", "Semolina, enriched", "Vital wheat gluten",
        "Soup, lentil with ham, canned", "Soup, vegetable beef, canned",
        "Soup, minestrone, canned", "Soup, tomato, canned",
    ],
    "dinner": [
        "Fish, salmon, Atlantic, farmed, cooked", "Fish, salmon, sockeye, cooked",
        "Fish, tuna, light, canned in water", "Fish, tuna, fresh, bluefin, cooked, dry heat",
        "Fish, cod, Atlantic, cooked", "Fish, tilapia, cooked", "Fish, haddock, cooked",
        "Fish, halibut, Atlantic and Pacific, cooked", "Fish, mackerel, Atlantic, cooked",
        "Fish, sardine, Atlantic, canned in oil", "Fish, trout, rainbow, farmed, cooked",
        "Fish, pollock, Alaska, cooked", "Fish, catfish, channel, farmed, cooked",
        "Fish, snapper, mixed species, cooked", "Fish, sea bass, mixed species, cooked",
        "Crustaceans, shrimp, cooked", "Crustaceans, crab, blue, cooked",
        "Crustaceans, lobster, northern, cooked", "Mollusks, mussel, blue, cooked",
        "Mollusks, oyster, eastern, farmed, cooked", "Mollusks, scallop, mixed species, cooked",
        "Mollusks, squid, mixed species, cooked",
        "Beef, round, top round, separable lean only",
        "Beef, loin, tenderloin steak, boneless, separable lean only",
        "Beef, ground, 90% lean meat / 10% fat, patty, cooked",
        "Beef, chuck", "Beef, loin, top sirloin",
        "Lamb, loin, separable lean only",
        "Lamb, leg, shank half, separable lean only",
        "Pork, fresh, loin, tenderloin, separable lean only, cooked",
        "Pork, fresh, loin, whole, separable lean only, cooked",
        "Pork, cured, ham, boneless, extra lean (approximately 5% fat), roasted",
        "Spinach, cooked, boiled", "Broccoli, cooked, boiled", "Cauliflower, cooked, boiled",
        "Carrots, cooked, boiled", "Carrots, raw", "Beans, snap, green, cooked, boiled",
        "Peas, green, cooked, boiled", "Asparagus, cooked, boiled",
        "Brussels sprouts, cooked, boiled", "Cabbage, cooked, boiled",
        "Cabbage, red, raw", "Kale, cooked, boiled", "Collards, cooked, boiled",
        "Mustard greens, cooked, boiled", "Chard, swiss, cooked, boiled",
        "Cabbage, chinese (pak-choi), cooked, boiled", "Squash, summer, all varieties, cooked, boiled",
        "Squash, winter, butternut, cooked, baked", "Squash, zucchini, baby, raw",
        "Eggplant, cooked, boiled", "Peppers, sweet, red, raw", "Peppers, sweet, green, raw",
        "Mushrooms, white, cooked, boiled", "Mushrooms, portabella, grilled",
        "Mushrooms, shiitake, cooked", "Onions, cooked, boiled", "Onions, raw",
        "Tomatoes, red, ripe, raw, year round average", "Tomatoes, red, ripe, cooked",
        "Cucumber, with peel, raw", "Lettuce, cos or romaine, raw", "Lettuce, iceberg",
        "Celery, raw", "Beets, cooked, boiled", "Turnips, cooked, boiled",
        "Parsnips, cooked, boiled", "Okra, cooked, boiled", "Artichokes, (globe or french), cooked, boiled",
        "Leeks, (bulb and lower leaf-portion), cooked, boiled", "Corn, sweet, yellow, cooked, boiled",
        "Potatoes, baked, flesh and skin", "Potatoes, boiled, cooked without skin, flesh",
        "Potatoes, mashed, prepared from granules", "Sweet potato, cooked, baked in skin",
        "Sweet potato, cooked, boiled, without skin", "Pumpkin, cooked, boiled",
        "Peas, edible-podded, cooked, boiled", "Alfalfa seeds, sprouted, raw",
        "Oil, olive, salad or cooking", "Oil, canola", "Oil, coconut", "Oil, sunflower",
        "Oil, sesame, salad or cooking", "Butter, salted", "Butter, Clarified butter (ghee)", "Oil, mustard",
    ],
    "snack": [
        "Apples, raw, with skin", "Bananas, raw", "Oranges, raw, all commercial varieties",
        "Strawberries, raw", "Blueberries, raw", "Raspberries, raw", "Blackberries, raw",
        "Grapes, red or green", "Watermelon, raw", "Melons, cantaloupe, raw", "Melons, honeydew, raw",
        "Pineapple, raw, all varieties", "Mangos, raw", "Papayas, raw", "Peaches, yellow, raw",
        "Pears, raw", "Plums, raw", "Cherries, sweet, raw", "Kiwifruit, green, raw",
        "Apricots, raw", "Pomegranates, raw", "Guavas, common, raw", "Figs, raw",
        "Dates, medjool", "Raisins, golden, seedless", "Plums, dried (prunes), uncooked",
        "Avocados, raw, all commercial varieties", "Tangerines, (mandarin oranges), raw",
        "Nectarines, raw", "Cranberries, raw", "Grapefruit, raw, pink and red and white",
        "Persimmons, japanese, raw", "Litchis, raw", "Passion-fruit, (granadilla), purple, raw",
        "Jackfruit, raw", "Nuts, coconut meat, raw", "Pummelo, raw",
        "Nuts, almonds", "Nuts, walnuts, english", "Nuts, cashew nuts, raw",
        "Nuts, pistachio nuts, raw", "Nuts, pecans", "Nuts, hazelnuts or filberts",
        "Nuts, macadamia nuts, raw", "Nuts, brazilnuts", "Peanuts, all types, raw",
        "Seeds, sunflower seed kernels, dried", "Seeds, pumpkin and squash seed kernels, dried",
        "Seeds, chia seeds, dried", "Seeds, flaxseed", "Seeds, sesame seeds, whole",
        "Seeds, hemp seed, hulled", "Nuts, chestnuts, european, roasted",
        "Snacks, popcorn, air-popped", "Snacks, rice cakes, brown rice, plain",
        "Snacks, granola bars, hard, plain", "Snacks, pretzels, hard, plain",
        "Snacks, tortilla chips, plain", "Snacks, trail mix, regular",
        "Crackers, whole-wheat", "Crackers, matzo, plain",
        "Orange juice, raw", "Apple juice, canned or bottled, unsweetened",
        "Tomato juice, canned", "Carrot juice, canned", "Grape juice, canned or bottled, unsweetened",
        "Beverages, almond milk, unsweetened", "Nuts, coconut water",
    ],
}

# Descriptions containing any of these are never used: organ meats, infant food, fried and battered
# preparations, confectionery, alcohol, and anything a meal planner should not suggest as a portion.
REJECT = re.compile(
    r"\b(babyfood|baby food|infant|formula|liver|kidney|brain|tongue|heart|spleen|lung|tripe|"
    r"gizzard|pancreas|thymus|blood|bone|carcass|variety meats|mechanically separated|giblets|"
    r"alcoholic|liqueur|wine|beer|vodka|whiskey|cocktail|candies|frosting|syrup|topping|"
    r"leavening|gelatin|shortening|lard|tallow|imitation|restaurant|fast ?food|school lunch|"
    r"unprepared|dehydrated|freeze-dried|with salt|battered|batter|fried|breaded|"
    r"solids and liquids|sweetened|added sugar|high fructose|reduced sodium, ready-to-serve)\b",
    re.IGNORECASE,
)
# Brand names appear in SR Legacy as all-caps words; a meal planner should stay generic.
BRAND = re.compile(r"\b[A-Z][A-Z'&.-]{2,}\b")
BRAND_OK = {"USDA", "RTC", "UHT"}

# Preparation preference, best first. A description matching an earlier pattern wins.
PREP_ORDER = (
    re.compile(r"cooked, (boiled|roasted|baked|steamed|grilled|moist heat|dry heat), .*without salt", re.I),
    re.compile(r"cooked, (boiled|roasted|baked|steamed|grilled|moist heat|dry heat)", re.I),
    re.compile(r"\b(cooked|roasted|baked|boiled|grilled|steamed)\b", re.I),
    re.compile(r"\braw\b", re.I),
)

MEAT = re.compile(r"\b(beef|pork|chicken|turkey|lamb|veal|duck|goose|bacon|ham|sausage|game|bison|rabbit|venison|gelatin)\b", re.I)
FISH = re.compile(r"\b(fish|salmon|tuna|cod|tilapia|sardine|mackerel|trout|haddock|anchovy|herring|pollock|halibut|snapper|catfish|bass|roe)\b", re.I)
SHELLFISH = re.compile(r"\b(shrimp|prawn|crab|lobster|oyster|clam|mussel|scallop|squid|octopus|crayfish|crustaceans|mollusks)\b", re.I)
DAIRY = re.compile(r"\b(milk|cheese|yogurt|yoghurt|butter|cream|kefir|ghee|whey|casein|paneer|ricotta|buttermilk)\b", re.I)
EGG = re.compile(r"\begg\b", re.I)
WHEAT = re.compile(r"\b(wheat|bread|pasta|noodle|cracker|flour|semolina|couscous|bulgur|cereal|biscuit|bagel|muffin|pancake|waffle|matzo|pretzel|spelt|rye|barley|farina|seitan|spaghetti|macaroni|granola)\b", re.I)
SOY = re.compile(r"\b(soy|soybean|tofu|tempeh|edamame|miso|natto)\b", re.I)
PEANUT = re.compile(r"\bpeanut", re.I)
TREE_NUT = re.compile(r"\b(almond|walnut|cashew|pecan|pistachio|hazelnut|filbert|macadamia|brazilnut|brazil nut|chestnut|coconut)\b", re.I)
SESAME = re.compile(r"\b(sesame|tahini|hummus)\b", re.I)
# Naturally gluten-free staples. Anything matching WHEAT above is never marked gluten-free.
GF_SAFE = re.compile(
    r"\b(rice|quinoa|millet|buckwheat|corn|maize|amaranth|sorghum|teff|potato|lentil|bean|pea|chickpea|"
    r"cowpea|soy|tofu|tempeh|nut|seed|fruit|vegetable|oil|egg|milk|cheese|yogurt)\b", re.I)
ANIMAL_CATEGORIES = {
    "Beef Products", "Pork Products", "Poultry Products", "Finfish and Shellfish Products",
    "Lamb, Veal, and Game Products", "Sausages and Luncheon Meats",
}
# Vegetables, fruit, pulses, nuts and plain meat/dairy cuts: whole foods, safe to call gluten-free.
WHOLE_FOOD_CATEGORIES = ANIMAL_CATEGORIES | {
    "Vegetables and Vegetable Products", "Fruits and Fruit Juices", "Legumes and Legume Products",
    "Nut and Seed Products", "Dairy and Egg Products", "Cereal Grains and Pasta", "Fats and Oils",
}


def prep_rank(description: str) -> int:
    for i, pattern in enumerate(PREP_ORDER):
        if pattern.search(description):
            return i
    return len(PREP_ORDER)


def usable(description: str) -> bool:
    if REJECT.search(description):
        return False
    return all(word.strip("'&.-") in BRAND_OK for word in BRAND.findall(description))


def classify(description: str, category: str) -> dict:
    """Assign allergens and diet tags from the description. Conservative where uncertain."""
    allergens = [
        name for pattern, name in (
            (DAIRY, "milk"), (EGG, "egg"), (FISH, "fish"), (SHELLFISH, "shellfish"),
            (TREE_NUT, "tree_nuts"), (PEANUT, "peanuts"), (WHEAT, "wheat"), (SOY, "soy"), (SESAME, "sesame"),
        ) if pattern.search(description)
    ]

    animal_flesh = category in ANIMAL_CATEGORIES or bool(
        MEAT.search(description) or FISH.search(description) or SHELLFISH.search(description))
    if animal_flesh:
        tags = []
    elif DAIRY.search(description) or EGG.search(description) or re.search(r"\bhoney\b", description, re.I):
        tags = ["vegetarian"]
    else:
        tags = ["vegan", "vegetarian"]

    if (category in WHOLE_FOOD_CATEGORIES or GF_SAFE.search(description)) and not WHEAT.search(description):
        tags.append("gluten_free")
    return {"allergens": allergens, "tags": tags}


# Portion units to try, in order, per USDA category. Energy-dense foods are measured in spoons and
# ounces: "1 cup" of sesame oil is a real USDA portion but not a thing anyone eats.
PORTION_UNITS = {
    "Fats and Oils": r"^(tbsp|tsp)",
    "Nut and Seed Products": r"^(oz|tbsp|cup)",
    "Spices and Herbs": r"^(tsp|tbsp)",
}
PORTION_DEFAULT = (r"^(cup|slice|piece|medium|large|fillet|fruit|container|scoop|breast|thigh|"
                   r"drumstick|link|patty|egg|bagel|muffin|roll|tortilla|bar|cake|cracker|oz|tbsp)")
PORTION_SMALL = r"^(tbsp|tsp|oz|slice|piece|small)"
# A single serving above this is not a serving. Anything larger is re-measured.
MAX_SERVING_KCAL = 400


def portion_for(portions: list[dict], category: str, energy_per_100g: float) -> tuple[str, float]:
    """Pick a household portion, preferring units that suit the food and capping its calories."""
    for pattern in (PORTION_UNITS.get(category, PORTION_DEFAULT), PORTION_SMALL):
        serving, grams = choose_portion(portions, pattern)
        if energy_per_100g * grams / 100.0 <= MAX_SERVING_KCAL:
            return serving, grams
    # No listed portion is small enough (oils, nut butters): state a gram weight of about 200 kcal.
    grams = max(5.0, round(200.0 / max(energy_per_100g, 1.0) * 100.0 / 5.0) * 5.0)
    return f"{grams:.0f} g", grams


def short_name(description: str) -> str:
    """Trim USDA's qualifier chain to something a meal plan can show.

    'Spinach, cooked, boiled, drained, without salt' -> 'Spinach, cooked, boiled'
    'Plums, dried (prunes), uncooked'                -> 'Plums, dried'

    Words that change what the food *is* are kept: dried plums carry four times the calories of
    fresh ones, so dropping "dried" would misdescribe the portion.
    """
    text = re.sub(r"\s*\(.*?\)", "", description)
    text = re.sub(r"\b(dry|moist) heat\b", "cooked", text, flags=re.I)  # USDA jargon
    text = re.sub(r",?\s*(broilers or fryers|domesticated|domestic|all commercial varieties|"
                  r"mixed species|all types|all varieties|mature seeds|immature seeds|"
                  r"separable lean only|separable lean and fat|boneless|from whole bird|retail parts|"
                  r"year round average|regular and quick|flesh and skin|with skin|without skin|"
                  r"all grades|choice|select|trimmed to [^,]*|approximately [^,]*|"
                  r"prepared with [^,]*|enriched|unenriched|regular|plain)\b", "", text, flags=re.I)
    parts = [p.strip() for p in text.split(",") if p.strip()]
    parts = [p for p in parts if not re.match(
        r"^(without|with|drained|solids|meat only|meat and skin|fluid|uncooked|seeded|seedless|"
        r"hulled|whole|large or small curd|home.prepared|air.popped|brown rice|hard)$", p, re.I)]
    prep = next((p for p in reversed(parts)
                 if re.match(r"^(roasted|baked|boiled|grilled|steamed|cooked|braised|broiled|raw|"
                             r"canned|dried|frozen|smoked)", p, re.I)), "")
    name = ", ".join(parts[:2])
    if prep and prep.lower() not in name.lower() and len(name) < 46:
        name = f"{name}, {prep}"
    name = re.sub(r"\s+", " ", name).strip(" ,")
    return (name[:1].upper() + name[1:])[:70]

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--usda-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()

    curated = list(csv.DictReader(args.out.open(encoding="utf-8")))
    have_ids = {r["fdc_id"] for r in curated}
    have_names = {r["food_name"].lower() for r in curated}
    print(f"keeping {len(curated)} hand-curated foods unchanged")

    categories = {c["id"]: c["description"] for c in read_csv(args.usda_dir / "food_category.csv")}
    foods = [f for f in read_csv(args.usda_dir / "food.csv")
             if f["data_type"] == "sr_legacy_food" and f["fdc_id"] not in have_ids and usable(f["description"])]

    # Resolve every wanted name to its best-ranked SR Legacy entry.
    picked: list[tuple[dict, str]] = []
    missing = []
    for meal, terms in WANTED.items():
        for term in terms:
            term, _, count = term.partition("*")
            matches = [f for f in foods if f["description"].lower().startswith(term.lower())]
            matches.sort(key=lambda f: (prep_rank(f["description"]), len(f["description"])))
            taken = 0
            for f in matches:
                if f["fdc_id"] in {p[0]["fdc_id"] for p in picked}:
                    continue
                picked.append((f, meal))
                taken += 1
                if taken >= int(count or 1):
                    break
            if not taken:
                missing.append(term)
    wanted_ids = {f["fdc_id"] for f, _ in picked}
    print(f"resolved {len(picked)} of {sum(len(t) for t in WANTED.values())} wanted names"
          + (f"; {len(missing)} not found: {', '.join(missing[:8])}" if missing else ""))

    nutrients: dict[str, dict[str, float]] = {}
    keys = set(NUTRIENTS.values()) | set(ENERGY_FALLBACKS)
    with (args.usda_dir / "food_nutrient.csv").open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row["fdc_id"] in wanted_ids and row["nutrient_id"] in keys and row["amount"]:
                nutrients.setdefault(row["fdc_id"], {})[row["nutrient_id"]] = float(row["amount"])
    portions: dict[str, list[dict]] = {}
    for row in read_csv(args.usda_dir / "food_portion.csv"):
        if row["fdc_id"] in wanted_ids:
            portions.setdefault(row["fdc_id"], []).append(row)

    added, skipped = [], []
    for food, meal in picked:
        per100 = nutrients.get(food["fdc_id"], {})
        energy = per100.get(NUTRIENTS["calories"]) or next((per100[k] for k in ENERGY_FALLBACKS if k in per100), None)
        if energy is None or any(NUTRIENTS[k] not in per100 for k in ("protein_g", "fat_g", "carbohydrates_g")):
            skipped.append(food["description"])
            continue
        name = short_name(food["description"])
        if name.lower() in have_names:
            continue
        have_names.add(name.lower())
        category = categories.get(food["food_category_id"], "")
        serving, grams = portion_for(portions.get(food["fdc_id"], []), category, energy)
        scale = grams / 100.0
        labels = classify(food["description"], category)
        added.append({
            "food_name": name,
            "serving_size": serving,
            "calories": round(energy * scale),
            "protein_g": round(per100[NUTRIENTS["protein_g"]] * scale, 1),
            "carbohydrates_g": round(per100[NUTRIENTS["carbohydrates_g"]] * scale, 1),
            "fat_g": round(per100[NUTRIENTS["fat_g"]] * scale, 1),
            "fiber_g": round(per100.get(NUTRIENTS["fiber_g"], 0.0) * scale, 1),
            "allergens": "|".join(labels["allergens"]),
            "dietary_tags": "|".join(labels["tags"]),
            "meal_category": meal,
            "serving_grams": round(grams, 1),
            "fdc_id": food["fdc_id"],
            "usda_description": food["description"],
            "source": "USDA FoodData Central SR Legacy 2018-04",
        })

    # A planner cannot build a portion out of a near-zero-energy entry (tea, brewed, 2 kcal/cup).
    added = [a for a in added if a["calories"] >= 10]

    rows = curated + added
    for i, row in enumerate(rows, start=1):
        row["food_id"] = i
    with args.out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(curated[0]))
        writer.writeheader()
        writer.writerows(rows)

    if skipped:
        print(f"skipped {len(skipped)} without complete nutrients: {', '.join(skipped[:5])}")
    print(f"wrote {len(rows)} foods ({len(curated)} curated + {len(added)} expanded)")
    print("by meal:", dict(collections.Counter(r["meal_category"] for r in rows)))
    print("vegetarian:", sum("vegetarian" in r["dietary_tags"] for r in rows),
          "| vegan:", sum("vegan" in r["dietary_tags"] for r in rows),
          "| gluten-free:", sum("gluten_free" in r["dietary_tags"] for r in rows))
    print("protein >=10 g/serving:", sum(float(r["protein_g"]) >= 10 for r in rows),
          "| vegetarian and >=10 g:", sum(float(r["protein_g"]) >= 10 and "vegetarian" in r["dietary_tags"] for r in rows))


if __name__ == "__main__":
    main()
