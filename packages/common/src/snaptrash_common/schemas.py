"""Shared Pydantic models — match Delta table columns exactly."""
from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel, Field


class FoodItem(BaseModel):
    type: str
    decay_stage: int = Field(ge=0, le=5)
    color_description: str | None = None
    mold_visible: bool = False
    estimated_kg: float = 0.0
    contaminated: bool = False
    compostable: bool = True

    # enriched (Stage 3)
    shelf_life_remaining_days: int | None = None
    dollar_value: float | None = None
    co2_kg: float | None = None


class PlasticItem(BaseModel):
    type: str
    resin_code: int | None = None
    color: str | None = None
    is_black_plastic: bool = False
    estimated_count: int = 1

    # enriched (Stage 4)
    polymer_type: str | None = None
    status: str | None = None  # recyclable | harmful | banned_<state>
    recyclable: bool | None = None
    harmful: bool | None = None
    alert: str | None = None


class GrokVisionResult(BaseModel):
    food_items: list[FoodItem] = []
    plastic_items: list[PlasticItem] = []
    # New top-level waste intelligence fields (used by future analytics)
    organics_percent: int = 50
    plastic_percent: int = 50
    fill_level_percent: int = 60
    contamination_severity: str = "medium"  # low | medium | high
    problematic_packaging: list[str] = []


class ScanRow(BaseModel):
    """Row in snaptrash.scans"""
    scan_id: str
    restaurant_id: str
    zip: str
    neighborhood: str
    timestamp: datetime
    food_kg: float
    compostable_kg: float
    contaminated_kg: float
    dollar_wastage: float
    co2_kg: float
    plastic_count: int
    harmful_plastic_count: int
    pet_kg: float
    ps_count: int
    food_items_json: str
    plastic_items_json: str


class InsightRow(BaseModel):
    restaurant_id: str
    computed_at: datetime
    weekly_dollar_waste: float
    forecast_next_week: float
    locality_percentile: float
    top_waste_category: str
    recommendation: str
    co2_avoided: float


class LocalityAggRow(BaseModel):
    zip: str
    neighborhood: str
    computed_at: datetime
    total_pet_kg: float
    total_ps_count: int
    harmful_count: int
    active_restaurants: int
    enzyme_alert: bool


class EnzymeAlertRow(BaseModel):
    alert_id: str
    zip: str
    neighborhood: str
    triggered_at: datetime
    pet_volume_7day: float
    threshold: float
    forecast_peak: float
    notified: bool
