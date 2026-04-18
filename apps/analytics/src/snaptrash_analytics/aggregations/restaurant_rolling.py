"""7-day rolling stats per restaurant. Writes top_waste_category + recommendation to insights."""
from __future__ import annotations
from datetime import datetime, timezone
from snaptrash_common.databricks_client import execute, fetch_all
from snaptrash_common.tables import SCANS, INSIGHTS


SQL_ROLLING = f"""
SELECT
  restaurant_id,
  SUM(dollar_wastage) AS weekly_dollar_waste,
  SUM(food_kg) AS weekly_food_kg,
  SUM(ps_count) AS weekly_ps_count,
  SUM(pet_kg) AS weekly_pet_kg,
  AVG(CASE WHEN food_kg > 0 THEN compostable_kg/food_kg END) AS compost_yield_rate,
  SUM(co2_kg) AS weekly_co2
FROM {SCANS}
WHERE timestamp >= now() - INTERVAL 7 DAYS
GROUP BY restaurant_id
"""


def recommendation(row: dict) -> str:
    if (row.get("weekly_ps_count") or 0) > 50:
        return "High PS foam usage — switch to PET clamshells."
    if (row.get("compost_yield_rate") or 0) < 0.5:
        return "Composting yield below 50%. Check contamination at source."
    if (row.get("weekly_dollar_waste") or 0) > 200:
        return "Weekly wastage > $200 — review portioning."
    return "On track. Maintain current practices."


def top_category(row: dict) -> str:
    if (row.get("weekly_ps_count") or 0) > 30:
        return "plastic"
    return "food"


def main():
    rows = fetch_all(SQL_ROLLING)
    now = datetime.now(timezone.utc).isoformat()
    for r in rows:
        execute(
            f"""
            INSERT INTO {INSIGHTS} VALUES (
              :restaurant_id, :computed_at, :weekly_dollar_waste,
              0.0, 0.0, :top, :rec, :co2
            )
            """,
            {
                "restaurant_id": r["restaurant_id"],
                "computed_at": now,
                "weekly_dollar_waste": float(r.get("weekly_dollar_waste") or 0),
                "top": top_category(r),
                "rec": recommendation(r),
                "co2": float(r.get("weekly_co2") or 0),
            },
        )
    print(f"✅ wrote {len(rows)} restaurant rolling rows")


if __name__ == "__main__":
    main()
