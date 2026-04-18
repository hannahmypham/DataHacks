"""Threshold detection — if locality PET > MSW baseline × 0.8 → enzyme alert."""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from snaptrash_common.databricks_client import execute, fetch_all
from snaptrash_common.tables import LOCALITY_AGG, MSW_BASELINE, ENZYME_ALERTS

# Treats CA as default state — extend with zip→state lookup later.
SQL_LATEST = f"""
WITH latest AS (
  SELECT zip, neighborhood, total_pet_kg, active_restaurants,
    ROW_NUMBER() OVER (PARTITION BY zip ORDER BY computed_at DESC) AS rn
  FROM {LOCALITY_AGG}
)
SELECT zip, neighborhood, total_pet_kg, active_restaurants
FROM latest WHERE rn = 1
"""

SQL_BASELINE = f"""
SELECT AVG(avg_commercial_waste_kg_per_restaurant) AS baseline
FROM {MSW_BASELINE}
WHERE state = :state AND year = (SELECT MAX(year) FROM {MSW_BASELINE} WHERE state = :state)
"""


def baseline_for_state(state: str = "CA") -> float:
    rows = fetch_all(SQL_BASELINE, {"state": state})
    if not rows or rows[0].get("baseline") is None:
        return 1000.0  # safe default
    return float(rows[0]["baseline"])


def main():
    base = baseline_for_state("CA")
    print(f"baseline kg/restaurant (CA): {base:.1f}")
    rows = fetch_all(SQL_LATEST)
    now = datetime.now(timezone.utc).isoformat()
    alerts = 0
    for r in rows:
        threshold = base * (r.get("active_restaurants") or 1) * 0.8
        pet = float(r.get("total_pet_kg") or 0)
        if pet > threshold:
            execute(
                f"""
                INSERT INTO {ENZYME_ALERTS} VALUES (
                  :id, :zip, :nb, :ts, :pet, :thr, :peak, false
                )
                """,
                {
                    "id": str(uuid.uuid4()),
                    "zip": r["zip"],
                    "nb": r.get("neighborhood") or "",
                    "ts": now,
                    "pet": pet,
                    "thr": threshold,
                    "peak": pet * 1.2,
                },
            )
            alerts += 1
    print(f"✅ {alerts} enzyme alerts emitted")


if __name__ == "__main__":
    main()
