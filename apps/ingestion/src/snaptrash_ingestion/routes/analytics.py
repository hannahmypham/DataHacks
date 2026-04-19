from __future__ import annotations

import logging
from fastapi import APIRouter, HTTPException

from snaptrash_common.databricks_client import fetch_all
from snaptrash_common.tables import INSIGHTS, LOCALITY_AGG, SCANS_UNIFIED

logger = logging.getLogger(__name__)

router = APIRouter(tags=["analytics"])


@router.get("/insights/{restaurant_id}")
def get_insights(restaurant_id: str):
    """Return the latest computed insights row for a restaurant."""
    try:
        rows = fetch_all(
            f"SELECT * FROM {INSIGHTS}"
            f" WHERE restaurant_id = :rid ORDER BY computed_at DESC LIMIT 1",
            {"rid": restaurant_id},
        )
    except Exception as exc:
        logger.error("insights query failed for %s: %s", restaurant_id, exc)
        raise HTTPException(503, f"Databricks unavailable: {exc}") from exc

    if not rows:
        raise HTTPException(404, f"No insights found for restaurant {restaurant_id!r}")

    return rows[0]


@router.get("/weekly-series/{restaurant_id}")
def get_weekly_series(restaurant_id: str):
    """Return last 7 days of daily food_kg actuals for the sparkline chart."""
    try:
        rows = fetch_all(
            f"""
            SELECT
              date_format(timestamp, 'E') AS day,
              CAST(dayofweek(timestamp) AS INT) AS dow,
              ROUND(SUM(food_kg), 2) AS actual
            FROM {SCANS_UNIFIED}
            WHERE restaurant_id = :rid
              AND timestamp >= current_timestamp() - INTERVAL 7 DAYS
            GROUP BY date_format(timestamp, 'E'), dayofweek(timestamp)
            ORDER BY dow
            """,
            {"rid": restaurant_id},
        )
    except Exception as exc:
        logger.error("weekly-series query failed for %s: %s", restaurant_id, exc)
        raise HTTPException(503, f"Databricks unavailable: {exc}") from exc

    # Collapse to Mon-Sun order (dayofweek: 1=Sun, 2=Mon … 7=Sat)
    dow_order = {2: "M", 3: "T", 4: "W", 5: "T", 6: "F", 7: "S", 1: "S"}
    out = []
    for r in rows:
        out.append({"day": dow_order.get(r["dow"], r["day"]), "actual": r["actual"]})

    return out


@router.get("/locality/{zip_code}")
def get_locality(zip_code: str):
    """Return the latest locality aggregation for a ZIP code."""
    try:
        rows = fetch_all(
            f"SELECT * FROM {LOCALITY_AGG}"
            f" WHERE zip = :z ORDER BY computed_at DESC LIMIT 1",
            {"z": zip_code},
        )
    except Exception as exc:
        logger.error("locality query failed for %s: %s", zip_code, exc)
        raise HTTPException(503, f"Databricks unavailable: {exc}") from exc

    if not rows:
        raise HTTPException(404, f"No locality data found for ZIP {zip_code!r}")

    return rows[0]
