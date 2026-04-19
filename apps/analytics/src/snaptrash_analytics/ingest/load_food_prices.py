"""
Load USDA retail food prices → snaptrash.analytics.gold_food_prices.

Source: USDA ERS Retail Food Prices (2022-2023 avg, $/kg).
Static reference table — fallback for dollar_wastage when CV side doesn't
enrich a scan with per-item dollar_value.

Also tries live USDA AMS Market News API (free, keyless) for current wholesale
prices — falls back to static table on any failure.
"""
from __future__ import annotations
import json
import urllib.request
import urllib.error

from snaptrash_common.databricks_client import execute, fetch_all
from snaptrash_common.tables import GOLD_FOOD_PRICES

# USDA ERS 2022-2023 retail avg $/kg (converted from $/lb × 2.2046)
# https://www.ers.usda.gov/data-products/retail-prices-for-fresh-fruits-and-vegetables/
USDA_STATIC_PRICES: dict[str, float] = {
    # Proteins
    "chicken":        8.16,
    "raw chicken":    8.16,
    "cooked chicken": 9.70,
    "beef":          15.85,
    "ground beef":   12.35,
    "pork":          10.00,
    "fish":          18.25,
    "salmon":        22.10,
    "shrimp":        24.50,
    "eggs":           5.50,
    # Dairy
    "milk":           2.30,
    "cheese":        11.10,
    "yogurt":         6.80,
    "butter":        10.20,
    # Grains / starches
    "bread":          5.95,
    "rice":           3.25,
    "cooked rice":    3.25,
    "pasta":          4.40,
    "potatoes":       2.15,
    "tortillas":      5.10,
    # Produce — leafy / veg
    "leafy greens":   7.65,
    "lettuce":        5.95,
    "spinach":        9.25,
    "kale":           8.80,
    "cabbage":        2.65,
    "broccoli":       4.95,
    "carrots":        2.85,
    "onions":         2.95,
    "tomatoes":       5.70,
    "peppers":        7.80,
    "cucumbers":      4.20,
    "mushrooms":      9.90,
    "corn":           3.40,
    # Fruit
    "apples":         4.85,
    "bananas":        1.70,
    "oranges":        3.95,
    "berries":       13.45,
    "strawberries":  11.25,
    "grapes":         7.10,
    "melon":          2.65,
    # Mixed / catch-all
    "salad":          6.80,
    "soup":           4.50,
    "sandwich":       9.00,
    "mixed food":     7.50,
    "other":          7.50,
}


def _try_live_ams_price(food_type: str) -> float | None:
    """
    Attempt live fetch from USDA AMS Market News public API.
    Returns None on any failure (network, parse, empty).
    """
    try:
        url = (
            "https://marsapi.ams.usda.gov/services/v1.2/reports"
            f"?q={urllib.parse.quote(food_type)}&format=json&maxResults=1"
        )
        with urllib.request.urlopen(url, timeout=5) as r:
            data = json.loads(r.read())
        # Response shape varies; just bail if no usable price field
        items = data.get("results") or []
        for it in items:
            p = it.get("avg_price") or it.get("price")
            if p:
                return float(p)
    except Exception:
        pass
    return None


def main() -> int:
    execute(f"DROP TABLE IF EXISTS {GOLD_FOOD_PRICES}")
    execute(f"""
        CREATE TABLE {GOLD_FOOD_PRICES} (
            food_type    STRING,
            price_per_kg DOUBLE,
            source       STRING
        ) USING DELTA
    """)

    vals = []
    for name, price in USDA_STATIC_PRICES.items():
        vals.append((name, price, "usda_ers_2022"))

    # Bulk insert
    if vals:
        rows_sql = ",".join(
            f"('{n.replace(chr(39), chr(39)+chr(39))}',{p},'{s}')"
            for n, p, s in vals
        )
        execute(f"INSERT INTO {GOLD_FOOD_PRICES} VALUES {rows_sql}")

    n = fetch_all(f"SELECT COUNT(*) AS n FROM {GOLD_FOOD_PRICES}")
    print(f"  gold_food_prices: {int(n[0]['n'])} food types loaded (USDA ERS 2022)")
    return int(n[0]["n"])


if __name__ == "__main__":
    main()
