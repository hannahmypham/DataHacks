from __future__ import annotations

import logging
from fastapi import APIRouter, HTTPException

from snaptrash_common.databricks_client import fetch_all
from snaptrash_common.tables import INSIGHTS, LOCALITY_AGG, SCANS_UNIFIED

logger = logging.getLogger(__name__)

router = APIRouter(tags=["analytics"])

# Databricks SQL warehouse returns every value as a string.
# These sets define which fields to cast so the frontend receives proper JSON types.
_FLOAT_FIELDS = {
    # insights — core metrics
    "weekly_dollar_waste", "weekly_food_kg", "weekly_plastic_count", "weekly_co2_kg",
    "compost_yield_rate", "contamination_rate",
    "forecast_food_kg", "forecast_dollar_waste", "forecast_plastic_count",
    "locality_percentile", "locality_percentile_pct",
    "better_than_count", "zip_restaurant_count",
    "sustainability_score",
    "peak_waste_day_kg", "at_risk_kg_24h",
    "nearest_facility_km", "nearest_facility_capacity_tons", "ca_network_capacity_tons",
    "co2_avoided", "shelf_life_min_days", "shelf_life_avg_days",
    "harmful_plastic_count", "ban_flag_count",
    "wcs_food_pct_restaurant", "wcs_food_pct_ca_avg", "wcs_gap",
    # insights — per-signal breakdown
    "signal_1", "signal_2", "signal_3", "signal_4", "signal_5",
    # locality
    "total_pet_kg", "total_ps_count", "harmful_count", "active_restaurants",
    "total_food_kg", "avg_food_kg_per_restaurant", "food_waste_per_capita_kg",
    "sd_county_avg_disposal_kg", "pct_vs_sd_avg", "avg_sustainability_score",
}
_BOOL_FIELDS = {"enzyme_alert", "recyclable"}


def _cast(row: dict) -> dict:
    """Cast string values from Databricks SQL warehouse to proper Python types.

    Only casts fields in explicit allowlists — all other fields kept as-is
    to avoid corrupting string fields like zip, neighborhood, badge_tier etc.
    """
    out = {}
    for k, v in row.items():
        if v is None or v == "null":
            out[k] = None
        elif k in _BOOL_FIELDS:
            out[k] = str(v).lower() not in ("false", "0", "")
        elif k in _FLOAT_FIELDS:
            try:
                out[k] = float(v)
            except (TypeError, ValueError):
                out[k] = v
        else:
            out[k] = v  # leave strings, timestamps, etc. untouched
    return out


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

    return _cast(rows[0])


@router.get("/weekly-series/{restaurant_id}")
def get_weekly_series(restaurant_id: str):
    """Return last 7 days of daily food_kg actuals for the sparkline chart."""
    try:
        rows = fetch_all(
            f"""
            SELECT
              date_format(timestamp, 'E') AS day_label,
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

    # dayofweek: 1=Sun, 2=Mon … 7=Sat — full names for display
    dow_order = {1: "Sunday", 2: "Monday", 3: "Tuesday", 4: "Wednesday", 5: "Thursday", 6: "Friday", 7: "Saturday"}
    out = []
    for r in rows:
        try:
            dow_int = int(r["dow"])  # cast from string
        except (TypeError, ValueError):
            dow_int = -1
        try:
            actual_float = float(r["actual"])
        except (TypeError, ValueError):
            actual_float = 0.0
        out.append({
            "day": dow_order.get(dow_int, str(r.get("day_label", "?"))),
            "actual": actual_float,
        })

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

    return _cast(rows[0])
