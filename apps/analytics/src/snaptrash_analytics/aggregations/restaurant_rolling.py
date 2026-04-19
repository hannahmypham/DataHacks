"""
7-day rolling aggregation per restaurant.

Computes:
  - food_kg, dollar_wastage, plastic totals
  - compost yield rate vs contamination rate
  - food category breakdown (from food_items_json)
  - plastic type frequency (from plastic_items_json)
  - peak waste day-of-week ("you waste more on Tuesdays")
  - WCS gap vs CA commercial benchmark
  - writes base row to snaptrash.insights (score added by sustainability_score.py)
"""
from __future__ import annotations
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from dateutil import parser as dtparser

from snaptrash_common.databricks_client import execute, fetch_all
from snaptrash_common.tables import (
    SCANS_UNIFIED, INSIGHTS, GOLD_WCS, GOLD_FOOD_PRICES, GOLD_SHELF_LIFE,
)

# CA commercial food benchmark — loaded from gold_wcs_benchmark at runtime
# Fallback if table not populated yet
CA_FOOD_PCT_FALLBACK = 17.7

# ---------------------------------------------------------------------------
# WCS category mapping — CV team sets wcs_category=null; map from food 'type'
# WCS categories: food | compostable_paper | yard_waste
# ---------------------------------------------------------------------------
_WCS_CATEGORY_MAP: dict[str, str] = {
    # protein / meat / seafood / dairy → food
    "raw chicken": "food", "cooked chicken": "food", "chicken": "food",
    "beef": "food", "pork": "food", "lamb": "food", "turkey": "food",
    "fish": "food", "seafood": "food", "shrimp": "food", "salmon": "food",
    "eggs": "food", "dairy": "food", "cheese": "food", "milk": "food",
    "yogurt": "food", "butter": "food",
    # produce → food
    "leafy greens": "food", "vegetables": "food", "vegetable": "food",
    "fruit": "food", "fruits": "food", "salad": "food", "tomato": "food",
    "onion": "food", "potato": "food", "corn": "food", "cucumber": "food",
    "carrot": "food", "broccoli": "food", "cauliflower": "food",
    # grains / prepared → food
    "cooked rice": "food", "rice": "food", "bread": "food", "pasta": "food",
    "noodles": "food", "cereal": "food", "tortilla": "food", "soup": "food",
    "stew": "food", "leftovers": "food", "mixed food": "food",
    # compostable paper / packaging → compostable_paper
    "paper": "compostable_paper", "cardboard": "compostable_paper",
    "paper napkin": "compostable_paper", "napkin": "compostable_paper",
    "paper bag": "compostable_paper", "paper cup": "compostable_paper",
    "paper plate": "compostable_paper", "tissue": "compostable_paper",
    "food-soiled paper": "compostable_paper", "wax paper": "compostable_paper",
    "parchment paper": "compostable_paper", "paper towel": "compostable_paper",
    # plants / organic → yard_waste
    "yard waste": "yard_waste", "plant": "yard_waste", "leaves": "yard_waste",
    "grass": "yard_waste", "herbs": "yard_waste", "flowers": "yard_waste",
    "wood": "yard_waste",
}


def _map_to_wcs_category(food_type: str) -> str:
    """Map CV food 'type' string → WCS category. Defaults to 'food'."""
    return _WCS_CATEGORY_MAP.get((food_type or "").strip().lower(), "food")


# ---------------------------------------------------------------------------
# SQL: 7-day rolling totals
# ---------------------------------------------------------------------------

SQL_ROLLING = f"""
SELECT
  restaurant_id,
  ANY_VALUE(zip)              AS zip,
  ANY_VALUE(neighborhood)     AS neighborhood,
  SUM(food_kg)                AS food_kg_7d,
  SUM(compostable_kg)         AS compost_kg_7d,
  SUM(contaminated_kg)        AS contam_kg_7d,
  SUM(dollar_wastage)         AS dollar_7d,
  SUM(co2_kg)                 AS co2_7d,
  SUM(plastic_count)          AS plastic_7d,
  SUM(harmful_plastic_count)  AS harmful_7d,
  SUM(pet_kg)                 AS pet_7d,
  SUM(ps_count)               AS ps_7d,
  COUNT(*)                    AS scan_count,
  COLLECT_LIST(food_items_json)    AS food_jsons,
  COLLECT_LIST(plastic_items_json) AS plastic_jsons
FROM {SCANS_UNIFIED}
WHERE timestamp >= NOW() - INTERVAL 7 DAYS
GROUP BY restaurant_id
"""

# Day-of-week breakdown (for "you waste more on Tuesdays" insight)
SQL_DOW = f"""
SELECT
  restaurant_id,
  DATE_FORMAT(timestamp, 'EEEE') AS day_of_week,
  SUM(food_kg)                    AS food_kg
FROM {SCANS_UNIFIED}
WHERE timestamp >= NOW() - INTERVAL 28 DAYS
GROUP BY restaurant_id, DATE_FORMAT(timestamp, 'EEEE')
"""


# ---------------------------------------------------------------------------
# Helpers: parse JSON arrays from scan rows
# ---------------------------------------------------------------------------

def _load_food_prices() -> dict[str, float]:
    """Load USDA $/kg price map from gold_food_prices. {} on any failure."""
    try:
        rows = fetch_all(f"SELECT food_type, price_per_kg FROM {GOLD_FOOD_PRICES}")
        return {r["food_type"].lower(): float(r["price_per_kg"]) for r in rows}
    except Exception:
        return {}


def _load_shelf_life() -> dict[str, int]:
    """Load USDA FoodKeeper days map from gold_food_shelf_life. {} on failure."""
    try:
        rows = fetch_all(
            f"SELECT food_type, shelf_life_days FROM {GOLD_SHELF_LIFE}"
        )
        return {r["food_type"].lower(): int(r["shelf_life_days"]) for r in rows}
    except Exception:
        return {}


def _shelf_life_days_for(food_type: str, shelf: dict[str, int]) -> int:
    """Exact → substring → default 3 days."""
    if not shelf:
        return 3
    t = (food_type or "").strip().lower()
    if t in shelf:
        return shelf[t]
    for key in shelf:
        if key in t or t in key:
            return shelf[key]
    return shelf.get("other", 3)


def _remaining_days(prepped_at: str | None, total_days: int, now: datetime) -> float:
    """
    shelf_life_remaining_days = total_shelf_life − days_since(prepped_at).
    If item lacks prepped_at (common when CV doesn't set it), assume it was
    prepped ~1 day ago — conservative "about to expire" default.
    """
    if not prepped_at:
        return max(0.0, total_days - 1.0)
    try:
        p = dtparser.isoparse(prepped_at)
        if p.tzinfo is None:
            p = p.replace(tzinfo=timezone.utc)
        age_days = (now - p).total_seconds() / 86400.0
        return round(max(0.0, total_days - age_days), 2)
    except Exception:
        return max(0.0, total_days - 1.0)


def _price_for(food_type: str, prices: dict[str, float]) -> float:
    """Look up $/kg for a food type. Exact match → substring match → default 7.50."""
    if not prices:
        return 7.50
    t = (food_type or "").strip().lower()
    if t in prices:
        return prices[t]
    for key in prices:
        if key in t or t in key:
            return prices[key]
    return prices.get("other", 7.50)


def _parse_food_jsons(
    json_list: list[str],
    prices: dict[str, float],
    shelf: dict[str, int],
    now: datetime,
) -> tuple[dict, float, dict]:
    """
    Aggregate food_items_json across all scans.
    Returns ({wcs_category: total_kg}, fallback_dollar_total, shelf_stats).

    fallback_dollar = SUM(item.estimated_kg × USDA_price[item.type]) ONLY for items
    where CV side didn't enrich with dollar_value. Used as a fallback to top up the
    scan-level dollar_wastage when CV omits the enrichment.

    shelf_stats = {
        "min_remaining_days": float,   # most-urgent item in the window
        "avg_remaining_days": float,   # kg-weighted average
        "at_risk_kg":         float,   # kg with ≤1 day remaining
        "sample_count":       int,
    }

    CV team always sets wcs_category=null — fall back to _map_to_wcs_category()
    which maps the food 'type' string (e.g. 'leafy greens') → WCS bucket.
    """
    category_kg: dict[str, float] = defaultdict(float)
    fallback_dollar = 0.0
    min_rem = None
    weighted_rem_sum = 0.0
    weighted_kg = 0.0
    at_risk_kg = 0.0
    sample_count = 0

    for js in json_list:
        if not js:
            continue
        try:
            items = json.loads(js)
            for item in items:
                ftype = item.get("type") or "food"
                wcs_cat = item.get("wcs_category") or _map_to_wcs_category(ftype)
                kg = float(item.get("estimated_kg") or 0)
                category_kg[wcs_cat] += kg
                # Dollar fallback — only if CV didn't enrich
                if not item.get("dollar_value") and kg > 0:
                    fallback_dollar += kg * _price_for(ftype, prices)
                # Shelf-life enrichment (analytics-side fallback when CV skips it).
                # Prefer CV-provided shelf_life_remaining_days; else compute from
                # prepped_at + USDA FoodKeeper total days.
                rem = item.get("shelf_life_remaining_days")
                if rem is None:
                    total_days = _shelf_life_days_for(ftype, shelf)
                    rem = _remaining_days(item.get("prepped_at"), total_days, now)
                rem = float(rem)
                sample_count += 1
                min_rem = rem if min_rem is None else min(min_rem, rem)
                if kg > 0:
                    weighted_rem_sum += rem * kg
                    weighted_kg += kg
                if rem <= 1.0 and kg > 0:
                    at_risk_kg += kg
        except (json.JSONDecodeError, TypeError):
            continue

    shelf_stats = {
        "min_remaining_days": round(min_rem, 2) if min_rem is not None else None,
        "avg_remaining_days": round(weighted_rem_sum / weighted_kg, 2) if weighted_kg > 0 else None,
        "at_risk_kg": round(at_risk_kg, 3),
        "sample_count": sample_count,
    }
    return dict(category_kg), round(fallback_dollar, 2), shelf_stats


def _parse_plastic_jsons(json_list: list[str]) -> dict:
    """
    Aggregate plastic_items_json across all scans.
    Returns polymer_counts dict: {polymer_type: count}
    """
    polymer_count: Counter = Counter()
    for js in json_list:
        if not js:
            continue
        try:
            items = json.loads(js)
            for item in items:
                polymer = item.get("polymer_type") or item.get("type") or "unknown"
                polymer_count[polymer] += int(item.get("estimated_count") or 1)
        except (json.JSONDecodeError, TypeError):
            continue
    return dict(polymer_count)


def _top_category(category_kg: dict[str, float]) -> str:
    if not category_kg:
        return "food"
    return max(category_kg, key=category_kg.get)


def _recommendation(row: dict, category_kg: dict, polymer_count: dict, peak_day: str | None, wcs_gap: float) -> str:
    """Rule-based recommendation string for the weekly insight card."""
    parts = []

    # WCS gap — primary signal
    if wcs_gap > 5:
        parts.append(
            f"Food waste is {wcs_gap:.1f}% above CA commercial average — "
            "review portion sizes or inventory ordering."
        )
    elif wcs_gap < -5:
        parts.append("Food waste composition is below CA commercial average. Keep it up.")

    # Peak day insight
    if peak_day:
        parts.append(f"Waste peaks on {peak_day}s — consider ordering less for that day.")

    # PS foam
    if (row.get("ps_7d") or 0) > 50:
        parts.append("High PS foam usage — PS is banned in CA. Switch to PET clamshells.")

    # Contamination
    contam_rate = (row.get("contam_kg_7d") or 0) / max(row.get("food_kg_7d") or 1, 0.001)
    if contam_rate > 0.3:
        parts.append(
            f"Contamination rate {contam_rate*100:.0f}% — segregate food before composting."
        )

    # Dollar wastage
    if (row.get("dollar_7d") or 0) > 300:
        parts.append(
            f"${row['dollar_7d']:.0f} wasted this week — "
            "align purchasing with actual demand."
        )

    # Compost yield
    compost_rate = (row.get("compost_kg_7d") or 0) / max(row.get("food_kg_7d") or 1, 0.001)
    if compost_rate < 0.4 and (row.get("food_kg_7d") or 0) > 2:
        parts.append("Compost yield under 40% — check for unnecessary contamination.")

    return " ".join(parts) if parts else "On track — maintain current waste practices."


# ---------------------------------------------------------------------------
# Fetch CA food benchmark from gold table
# ---------------------------------------------------------------------------

def _ca_food_pct() -> float:
    try:
        rows = fetch_all(
            f"SELECT material_pct FROM {GOLD_WCS} WHERE material = 'food' LIMIT 1"
        )
        if rows:
            return float(rows[0]["material_pct"])
    except Exception:
        pass
    return CA_FOOD_PCT_FALLBACK


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    rows = fetch_all(SQL_ROLLING)
    dow_rows = fetch_all(SQL_DOW)
    ca_food_pct = _ca_food_pct()
    prices = _load_food_prices()
    shelf = _load_shelf_life()
    print(f"CA commercial food benchmark: {ca_food_pct:.1f}%")
    print(f"USDA food price map: {len(prices)} entries")
    print(f"USDA FoodKeeper shelf-life map: {len(shelf)} entries")

    # Build day-of-week peak map: {restaurant_id: (peak_day, peak_kg)}
    dow_map: dict[str, tuple[str, float]] = {}
    dow_data: dict[str, dict[str, float]] = defaultdict(dict)
    for d in dow_rows:
        rid = d["restaurant_id"]
        dow_data[rid][d["day_of_week"]] = float(d.get("food_kg") or 0)
    for rid, days in dow_data.items():
        peak_day = max(days, key=days.get)
        dow_map[rid] = (peak_day, days[peak_day])

    now_dt = datetime.now(timezone.utc)
    now = now_dt.isoformat()
    written = 0

    for r in rows:
        rid = r["restaurant_id"]
        food_kg = float(r.get("food_kg_7d") or 0)
        plastic_kg_proxy = float(r.get("pet_7d") or 0) + (float(r.get("ps_7d") or 0) * 0.05)
        total_waste_kg = food_kg + plastic_kg_proxy

        # WCS gap: restaurant food% vs CA avg
        restaurant_food_pct = (food_kg / total_waste_kg * 100) if total_waste_kg > 0 else 0.0
        wcs_gap = round(restaurant_food_pct - ca_food_pct, 2)

        # Food category breakdown
        food_jsons = r.get("food_jsons") or []
        if isinstance(food_jsons, str):
            food_jsons = [food_jsons]
        category_kg, fallback_dollar, shelf_stats = _parse_food_jsons(
            food_jsons, prices, shelf, now_dt
        )

        plastic_jsons = r.get("plastic_jsons") or []
        if isinstance(plastic_jsons, str):
            plastic_jsons = [plastic_jsons]
        polymer_count = _parse_plastic_jsons(plastic_jsons)

        top_cat = _top_category(category_kg)

        peak_day, peak_kg = dow_map.get(rid, (None, 0.0))

        rec = _recommendation(r, category_kg, polymer_count, peak_day, wcs_gap)
        # Shelf-life urgency addendum — surfaces the "cook-or-toss" flag.
        at_risk_kg = shelf_stats.get("at_risk_kg") or 0.0
        min_rem = shelf_stats.get("min_remaining_days")
        if at_risk_kg >= 1.0:
            rec = (
                f"{at_risk_kg:.1f} kg expiring within 24h — prioritize those items. "
                + rec
            )
        elif isinstance(min_rem, (int, float)) and min_rem <= 2.0:
            rec = (
                f"Oldest item has {min_rem:.1f} days of shelf life left. "
                + rec
            )

        compost_rate = (float(r.get("compost_kg_7d") or 0) /
                        max(food_kg, 0.001))
        contam_rate = (float(r.get("contam_kg_7d") or 0) /
                       max(food_kg, 0.001))
        co2_avoided = float(r.get("compost_kg_7d") or 0) * 2.5  # ~2.5 kg CO2 per kg compost

        execute(f"""
            INSERT INTO {INSIGHTS} (
              restaurant_id, computed_at,
              zip, neighborhood,
              weekly_food_kg, weekly_dollar_waste, weekly_plastic_count,
              weekly_co2_kg, compost_yield_rate, contamination_rate,
              forecast_food_kg, forecast_dollar_waste,
              forecast_plastic_count,
              wcs_food_pct_restaurant, wcs_food_pct_ca_avg, wcs_gap,
              nearest_facility_name, nearest_facility_km,
              locality_percentile, locality_percentile_pct,
              zip_restaurant_count, better_than_count,
              sustainability_score, badge_tier,
              peak_waste_day, peak_waste_day_kg,
              top_waste_category, recommendation,
              score_feedback_message, co2_avoided,
              shelf_life_min_days, shelf_life_avg_days, at_risk_kg_24h
            ) VALUES (
              :rid, :ts,
              :zip, :nb,
              :food_kg, :dollar, :plastic,
              :co2, :compost_rate, :contam_rate,
              0.0, 0.0, 0,
              :rest_food_pct, :ca_food_pct, :wcs_gap,
              NULL, NULL,
              0.0, 0, 0, 0,
              0.0, NULL,
              :peak_day, :peak_kg,
              :top_cat, :rec,
              '', :co2_avoided,
              :sl_min, :sl_avg, :sl_risk
            )
        """, {
            "rid": rid,
            "ts": now,
            "zip": r.get("zip") or "",
            "nb": r.get("neighborhood") or "",
            "food_kg": food_kg,
            # Dollar: prefer CV-enriched dollar_wastage; fall back to USDA price × kg
            "dollar": float(r.get("dollar_7d") or 0) or fallback_dollar,
            "plastic": int(r.get("plastic_7d") or 0),
            "co2": float(r.get("co2_7d") or 0),
            "compost_rate": round(compost_rate, 3),
            "contam_rate": round(contam_rate, 3),
            "rest_food_pct": round(restaurant_food_pct, 2),
            "ca_food_pct": ca_food_pct,
            "wcs_gap": wcs_gap,
            "peak_day": peak_day,
            "peak_kg": round(peak_kg, 2),
            "top_cat": top_cat,
            "rec": rec,
            "co2_avoided": round(co2_avoided, 2),
            "sl_min": shelf_stats.get("min_remaining_days"),
            "sl_avg": shelf_stats.get("avg_remaining_days"),
            "sl_risk": at_risk_kg,
        })
        written += 1

    print(f"✅ {written} restaurant rolling rows written to {INSIGHTS}")


if __name__ == "__main__":
    main()
