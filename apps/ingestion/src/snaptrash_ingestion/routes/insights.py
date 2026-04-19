from __future__ import annotations
from fastapi import APIRouter, HTTPException
from snaptrash_common.databricks_client import fetch_all
from snaptrash_common.tables import INSIGHTS, LOCALITY_AGG

router = APIRouter(tags=["insights"])


@router.get("/insights/{restaurant_id}")
def get_insights(restaurant_id: str):
    rows = fetch_all(
        f"SELECT * FROM {INSIGHTS} WHERE restaurant_id = :rid ORDER BY computed_at DESC LIMIT 1",
        {"rid": restaurant_id},
    )
    if not rows:
        raise HTTPException(404, f"No insights found for {restaurant_id}")
    return rows[0]


@router.get("/locality/{zip_code}")
def get_locality(zip_code: str):
    rows = fetch_all(
        f"SELECT * FROM {LOCALITY_AGG} WHERE zip = :z ORDER BY computed_at DESC LIMIT 1",
        {"z": zip_code},
    )
    if not rows:
        raise HTTPException(404, f"No locality data found for ZIP {zip_code}")
    return rows[0]
