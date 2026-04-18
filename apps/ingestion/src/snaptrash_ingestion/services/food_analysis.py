"""Stage 3 — enrich FoodItem with shelf life, $, CO2.

Placeholder lookup tables. Swap for USDA FoodKeeper API + USDA retail prices later.
"""
from __future__ import annotations
from snaptrash_common.schemas import FoodItem

# kg shelf life (refrigerated)
DEFAULT_SHELF_LIFE_DAYS = 5
SHELF_LIFE: dict[str, int] = {
    "leafy greens": 5,
    "raw chicken": 2,
    "cooked rice": 5,
    "bread": 7,
    "dairy": 7,
    "fish": 2,
    "beef": 3,
    "pork": 3,
    "fruit": 7,
    "vegetables": 7,
}

# $/kg (USDA avg retail, placeholder)
PRICE_PER_KG: dict[str, float] = {
    "leafy greens": 4.0,
    "raw chicken": 6.5,
    "cooked rice": 3.0,
    "bread": 4.0,
    "dairy": 5.0,
    "fish": 18.0,
    "beef": 12.0,
    "pork": 8.0,
    "fruit": 4.5,
    "vegetables": 3.5,
}

# kg CO2 per kg food (FAO factors, placeholder)
CO2_PER_KG: dict[str, float] = {
    "leafy greens": 1.7,
    "raw chicken": 6.9,
    "cooked rice": 4.5,
    "bread": 1.6,
    "dairy": 3.2,
    "fish": 5.4,
    "beef": 27.0,
    "pork": 12.1,
    "fruit": 1.1,
    "vegetables": 2.0,
}

DEFAULT_PRICE = 4.0
DEFAULT_CO2 = 2.5


def _key(food_type: str) -> str:
    t = food_type.lower().strip()
    for k in SHELF_LIFE:
        if k in t or t in k:
            return k
    return ""


def enrich(item: FoodItem) -> FoodItem:
    k = _key(item.type)
    shelf = SHELF_LIFE.get(k, DEFAULT_SHELF_LIFE_DAYS)
    decay_days = item.decay_stage  # rough: 1 day per stage
    item.shelf_life_remaining_days = max(0, shelf - decay_days)

    item.dollar_value = item.estimated_kg * PRICE_PER_KG.get(k, DEFAULT_PRICE)
    item.co2_kg = item.estimated_kg * CO2_PER_KG.get(k, DEFAULT_CO2)

    if item.decay_stage >= 4 or item.mold_visible:
        item.contaminated = True
        item.compostable = False
    return item
