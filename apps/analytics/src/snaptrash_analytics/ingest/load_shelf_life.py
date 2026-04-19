"""
Load USDA FoodKeeper shelf-life data → snaptrash.analytics.gold_food_shelf_life.

Source: USDA FoodKeeper (FSIS / FoodSafety.gov) curated pantry/fridge shelf
life days. Static reference table — fallback when a CV scan doesn't enrich an
item with per-item shelf_life_days.

FoodKeeper stopped exposing a public JSON endpoint in 2023; values below are
transcribed from the current FoodKeeper mobile app and the FSIS fact sheets.

Columns:
  food_type        STRING  lower-cased item key (matches CV `type`)
  shelf_life_days  INT     fridge shelf life (days) for a freshly-prepped item
  category         STRING  protein | dairy | produce | grain | prepared | other
  source           STRING  provenance tag
"""
from __future__ import annotations

from snaptrash_common.databricks_client import execute, fetch_all
from snaptrash_common.tables import GOLD_SHELF_LIFE

# USDA FoodKeeper fridge shelf life (cooked/prepped, 40°F)
# https://www.foodsafety.gov/keep-food-safe/foodkeeper-app
USDA_FOODKEEPER: dict[str, tuple[int, str]] = {
    # --- Proteins (cooked) ---
    "chicken":        (3,  "protein"),
    "raw chicken":    (2,  "protein"),
    "cooked chicken": (4,  "protein"),
    "beef":           (3,  "protein"),
    "ground beef":    (2,  "protein"),
    "pork":           (3,  "protein"),
    "lamb":           (3,  "protein"),
    "turkey":         (4,  "protein"),
    "fish":           (2,  "protein"),
    "salmon":         (2,  "protein"),
    "shrimp":         (3,  "protein"),
    "seafood":        (2,  "protein"),
    "eggs":          (21,  "protein"),
    # --- Dairy ---
    "milk":           (7,  "dairy"),
    "cheese":        (21,  "dairy"),
    "yogurt":        (14,  "dairy"),
    "butter":        (30,  "dairy"),
    # --- Grains / starches (cooked) ---
    "bread":          (7,  "grain"),
    "rice":           (5,  "grain"),
    "cooked rice":    (5,  "grain"),
    "pasta":          (5,  "grain"),
    "noodles":        (5,  "grain"),
    "potatoes":      (14,  "grain"),
    "tortillas":      (7,  "grain"),
    "cereal":        (90,  "grain"),
    # --- Produce — leafy / veg ---
    "leafy greens":   (5,  "produce"),
    "lettuce":        (7,  "produce"),
    "spinach":        (5,  "produce"),
    "kale":           (7,  "produce"),
    "cabbage":       (30,  "produce"),
    "broccoli":       (7,  "produce"),
    "cauliflower":    (7,  "produce"),
    "carrots":       (30,  "produce"),
    "onions":        (60,  "produce"),
    "tomatoes":       (7,  "produce"),
    "tomato":         (7,  "produce"),
    "peppers":        (7,  "produce"),
    "cucumbers":      (7,  "produce"),
    "cucumber":       (7,  "produce"),
    "mushrooms":      (5,  "produce"),
    "corn":           (3,  "produce"),
    # --- Fruit ---
    "apples":        (30,  "produce"),
    "bananas":        (5,  "produce"),
    "oranges":       (14,  "produce"),
    "berries":        (3,  "produce"),
    "strawberries":   (3,  "produce"),
    "grapes":         (7,  "produce"),
    "melon":          (5,  "produce"),
    # --- Prepared / catch-all ---
    "salad":          (3,  "prepared"),
    "soup":           (4,  "prepared"),
    "stew":           (4,  "prepared"),
    "sandwich":       (2,  "prepared"),
    "leftovers":      (4,  "prepared"),
    "mixed food":     (3,  "prepared"),
    "other":          (3,  "other"),
}


def main() -> int:
    execute(f"DROP TABLE IF EXISTS {GOLD_SHELF_LIFE}")
    execute(f"""
        CREATE TABLE {GOLD_SHELF_LIFE} (
            food_type        STRING,
            shelf_life_days  INT,
            category         STRING,
            source           STRING
        ) USING DELTA
    """)

    vals = [
        (name, days, cat, "usda_foodkeeper_2024")
        for name, (days, cat) in USDA_FOODKEEPER.items()
    ]
    if vals:
        rows_sql = ",".join(
            f"('{n.replace(chr(39), chr(39)+chr(39))}',{d},'{c}','{s}')"
            for n, d, c, s in vals
        )
        execute(f"INSERT INTO {GOLD_SHELF_LIFE} VALUES {rows_sql}")

    n = fetch_all(f"SELECT COUNT(*) AS n FROM {GOLD_SHELF_LIFE}")
    print(f"  gold_food_shelf_life: {int(n[0]['n'])} food types loaded "
          f"(USDA FoodKeeper 2024)")
    return int(n[0]["n"])


if __name__ == "__main__":
    main()
