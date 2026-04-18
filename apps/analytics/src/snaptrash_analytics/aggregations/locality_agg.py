"""Locality (zip) aggregation → snaptrash.locality_agg."""
from __future__ import annotations
from datetime import datetime, timezone
from snaptrash_common.databricks_client import execute, fetch_all
from snaptrash_common.tables import SCANS, LOCALITY_AGG

SQL = f"""
SELECT
  zip,
  ANY_VALUE(neighborhood) AS neighborhood,
  SUM(pet_kg) AS total_pet_kg,
  SUM(ps_count) AS total_ps_count,
  SUM(harmful_plastic_count) AS harmful_count,
  COUNT(DISTINCT restaurant_id) AS active_restaurants
FROM {SCANS}
WHERE timestamp >= now() - INTERVAL 7 DAYS
GROUP BY zip
"""


def main():
    rows = fetch_all(SQL)
    now = datetime.now(timezone.utc).isoformat()
    for r in rows:
        execute(
            f"""
            INSERT INTO {LOCALITY_AGG} VALUES (
              :zip, :nb, :computed_at,
              :pet, :ps, :harm, :active, false
            )
            """,
            {
                "zip": r["zip"],
                "nb": r.get("neighborhood") or "",
                "computed_at": now,
                "pet": float(r.get("total_pet_kg") or 0),
                "ps": int(r.get("total_ps_count") or 0),
                "harm": int(r.get("harmful_count") or 0),
                "active": int(r.get("active_restaurants") or 0),
            },
        )
    print(f"✅ wrote {len(rows)} locality rows")


if __name__ == "__main__":
    main()
