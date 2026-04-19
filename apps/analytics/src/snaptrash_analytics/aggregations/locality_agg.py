"""
Locality (ZIP) aggregation → snaptrash.locality_agg.

Computes per ZIP:
  - Plastic totals (PET, PS, harmful)
  - Food totals + per-capita (vs SD county benchmark)
  - Active restaurant count
  - Avg sustainability score across restaurants in ZIP
  - Enzyme alert flag

Reads SD county per-capita benchmark from gold_sd_disposal_ts (power2_impexp data).
"""
from __future__ import annotations
from datetime import datetime, timezone

from snaptrash_common.databricks_client import execute, fetch_all
from snaptrash_common.tables import (
    SCANS_UNIFIED, INSIGHTS, LOCALITY_AGG, GOLD_SD_DISPOSAL, GOLD_SD_POPULATION,
    GOLD_SD_ZIP_POP,
)

# Fallback if gold table not yet populated
SD_COUNTY_POP_FALLBACK = 3_338_330


def _sd_county_pop() -> int:
    """Pull latest SD county pop from gold_sd_population (long format)."""
    try:
        rows = fetch_all(
            f"SELECT population FROM {GOLD_SD_POPULATION} ORDER BY year DESC LIMIT 1"
        )
        if rows and rows[0].get("population"):
            return int(rows[0]["population"])
    except Exception:
        pass
    return SD_COUNTY_POP_FALLBACK


def _zip_pop_map() -> dict[str, int]:
    """Per-ZIP population from Census ACS (gold_sd_zip_pop). Empty dict on failure."""
    try:
        rows = fetch_all(f"SELECT zip, population FROM {GOLD_SD_ZIP_POP}")
        return {r["zip"]: int(r["population"]) for r in rows if r.get("population")}
    except Exception:
        return {}


SQL_LOCALITY = f"""
SELECT
  zip,
  ANY_VALUE(neighborhood)         AS neighborhood,
  SUM(pet_kg)                     AS total_pet_kg,
  SUM(ps_count)                   AS total_ps_count,
  SUM(harmful_plastic_count)      AS harmful_count,
  COUNT(DISTINCT restaurant_id)   AS active_restaurants,
  SUM(food_kg)                    AS total_food_kg,
  AVG(food_kg)                    AS avg_food_kg_per_restaurant
FROM {SCANS_UNIFIED}
WHERE timestamp >= NOW() - INTERVAL 7 DAYS
GROUP BY zip
"""

SQL_AVG_SCORE = f"""
SELECT zip, AVG(sustainability_score) AS avg_score
FROM {INSIGHTS}
WHERE computed_at >= NOW() - INTERVAL 2 HOURS
  AND sustainability_score IS NOT NULL
GROUP BY zip
"""


def _sd_avg_disposal_kg() -> float:
    """Latest SD county per-capita disposal from gold table (power2_impexp)."""
    try:
        rows = fetch_all(f"""
            SELECT disposal_per_capita_kg
            FROM {GOLD_SD_DISPOSAL}
            WHERE county = 'san diego'
            ORDER BY year DESC
            LIMIT 1
        """)
        if rows:
            return float(rows[0]["disposal_per_capita_kg"])
    except Exception:
        pass
    # Fallback: SD 2019 ≈ 3.2M tons × 907.185 kg/ton / 3.34M people
    return 868.0  # kg/person/yr


def main():
    rows = fetch_all(SQL_LOCALITY)
    score_rows = fetch_all(SQL_AVG_SCORE)
    sd_avg_kg = _sd_avg_disposal_kg()
    sd_county_pop = _sd_county_pop()
    zip_pop_map = _zip_pop_map()
    fallback_zip_pop = max(1, sd_county_pop // 115)
    print(f"SD county population: {sd_county_pop:,}")
    print(f"Per-ZIP pop: {len(zip_pop_map)} Census ZIPs loaded "
          f"(fallback={fallback_zip_pop:,})")
    print(f"SD county avg disposal benchmark: {sd_avg_kg:.0f} kg/person/yr")

    # Build score map per ZIP
    score_map = {r["zip"]: float(r.get("avg_score") or 0) for r in score_rows}

    now = datetime.now(timezone.utc).isoformat()
    written = 0

    for r in rows:
        zip_code = r["zip"]
        total_food_kg = float(r.get("total_food_kg") or 0)

        # Real per-ZIP pop from Census ACS; fallback to county/115
        zip_pop = zip_pop_map.get(zip_code, fallback_zip_pop)

        food_per_capita = total_food_kg / zip_pop

        # Annualize 7-day total × 52 weeks, divide by ZIP pop
        annual_food_per_capita = total_food_kg * 52 / zip_pop
        pct_vs_sd = (annual_food_per_capita / sd_avg_kg - 1.0) if sd_avg_kg > 0 else 0.0

        avg_score = score_map.get(zip_code, 0.0)

        # Enzyme alert: total_pet_kg > 80% of MSW baseline threshold
        # Threshold re-derived here — threshold_check.py handles authoritative alerts
        pet_7d = float(r.get("total_pet_kg") or 0)
        active = int(r.get("active_restaurants") or 0)
        enzyme_alert = pet_7d > (active * 50 * 0.8)  # 50 kg/restaurant baseline × 80%

        execute(f"""
            INSERT INTO {LOCALITY_AGG} (
              zip, neighborhood, computed_at,
              total_pet_kg, total_ps_count, harmful_count,
              active_restaurants,
              total_food_kg, avg_food_kg_per_restaurant,
              food_waste_per_capita_kg,
              sd_county_avg_disposal_kg, pct_vs_sd_avg,
              avg_sustainability_score,
              enzyme_alert
            ) VALUES (
              :zip, :nb, :ts,
              :pet, :ps, :harm,
              :active,
              :food_kg, :avg_food,
              :per_cap,
              :sd_avg, :pct_vs_sd,
              :avg_score,
              :enzyme
            )
        """, {
            "zip": zip_code,
            "nb": r.get("neighborhood") or "",
            "ts": now,
            "pet": pet_7d,
            "ps": int(r.get("total_ps_count") or 0),
            "harm": int(r.get("harmful_count") or 0),
            "active": active,
            "food_kg": total_food_kg,
            "avg_food": float(r.get("avg_food_kg_per_restaurant") or 0),
            "per_cap": round(food_per_capita, 4),
            "sd_avg": sd_avg_kg,
            "pct_vs_sd": round(pct_vs_sd, 4),
            "avg_score": round(avg_score, 1),
            "enzyme": enzyme_alert,
        })
        written += 1

    print(f"✅ {written} locality rows written to {LOCALITY_AGG}")


if __name__ == "__main__":
    main()
