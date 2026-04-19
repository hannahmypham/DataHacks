from __future__ import annotations

import logging
from fastapi import APIRouter, HTTPException

from snaptrash_common.databricks_client import fetch_all
from snaptrash_common.tables import INSIGHTS, LOCALITY_AGG

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
