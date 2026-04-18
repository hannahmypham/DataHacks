"""Stage 5 — append a ScanRow to snaptrash.scans Delta table."""
from __future__ import annotations
from snaptrash_common.databricks_client import execute
from snaptrash_common.tables import SCANS
from snaptrash_common.schemas import ScanRow


INSERT_SQL = f"""
INSERT INTO {SCANS} VALUES (
    :scan_id, :restaurant_id, :zip, :neighborhood, :timestamp,
    :food_kg, :compostable_kg, :contaminated_kg,
    :dollar_wastage, :co2_kg,
    :plastic_count, :harmful_plastic_count,
    :pet_kg, :ps_count,
    :food_items_json, :plastic_items_json
)
"""


def insert_scan(row: ScanRow) -> None:
    params = row.model_dump()
    params["timestamp"] = row.timestamp.isoformat()
    execute(INSERT_SQL, params)
