"""Read funcs for FastAPI integration. Imported by ingestion app's routes/ during integration phase."""
from __future__ import annotations
from snaptrash_common.databricks_client import fetch_all
from snaptrash_common.tables import INSIGHTS, LOCALITY_AGG, SCANS, ENZYME_ALERTS


def latest_insight(restaurant_id: str) -> dict | None:
    rows = fetch_all(
        f"SELECT * FROM {INSIGHTS} WHERE restaurant_id = :rid ORDER BY computed_at DESC LIMIT 1",
        {"rid": restaurant_id},
    )
    return rows[0] if rows else None


def latest_locality(zip_code: str) -> dict | None:
    rows = fetch_all(
        f"SELECT * FROM {LOCALITY_AGG} WHERE zip = :z ORDER BY computed_at DESC LIMIT 1",
        {"z": zip_code},
    )
    return rows[0] if rows else None


def scan_by_id(scan_id: str) -> dict | None:
    rows = fetch_all(f"SELECT * FROM {SCANS} WHERE scan_id = :sid", {"sid": scan_id})
    return rows[0] if rows else None


def pending_enzyme_alerts() -> list[dict]:
    return fetch_all(f"SELECT * FROM {ENZYME_ALERTS} WHERE notified = false")
