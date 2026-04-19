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
    estimated_kg: float = 0.0  # new for sustainability total_plastic_kg

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
    similarity_score: float = 1.0
    cache_hit: bool = False


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
    total_plastic_kg: float = 0.0
    ban_flag_count: int = 0
    recyclable_count: int = 0
    food_items_json: str
    plastic_items_json: str


class InsightRow(BaseModel):
    restaurant_id: str
    computed_at: datetime
    weekly_food_kg: float = 0.0
    weekly_dollar_waste: float = 0.0
    weekly_plastic_count: int = 0
    weekly_co2_kg: float = 0.0
    forecast_food_kg: float = 0.0
    forecast_dollar_waste: float = 0.0
    forecast_plastic_count: int = 0
    locality_percentile: float = 0.0
    locality_percentile_pct: int = 0
    better_than_count: int = 0
    zip_restaurant_count: int = 0
    sustainability_score: float = 1.0  # 1–4 scale
    signal_1: float = 0.0
    signal_2: float = 0.0
    signal_3: float = 0.0
    signal_4: float = 0.0
    signal_5: float = 0.0
    badge_tier: str | None = None
    tier_emoji: str | None = None
    tier_key: str | None = None
    peak_waste_day: str | None = None
    peak_waste_day_kg: float = 0.0
    top_waste_category: str | None = None
    recommendation: str | None = None
    score_feedback_message: str | None = None
    co2_avoided: float = 0.0
    shelf_life_min_days: float = 0.0
    shelf_life_avg_days: float = 0.0
    at_risk_kg_24h: float = 0.0
    nearest_facility_name: str | None = None
    nearest_facility_km: float | None = None
    harmful_plastic_count: float = 0.0
    ban_flag_count: float = 0.0


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


class PlasticReportContext(BaseModel):
    """Context passed to Vapi assistant (variableValues) OR SMTP email reports.
    Used by both voice alerts and new email alerts (per plan)."""
    locality: str
    neighborhood: str
    total_plastic_kg: float
    harmful_count: int
    pet_kg: float
    weekly_plastic_count: int
    active_restaurants: int
    threshold: float = 150.0
    lab_recommendation: str = "Contact BluumBio (Berkeley, CA) for plastic-eating enzymes from the CSV data."
    stats_summary: str
    forecast_note: str = "Prophet forecast indicates continued high waste without intervention."
    action_call: str = "Reduce single-use plastics and switch to compostable alternatives."


class VoiceAlertRow(BaseModel):
    """Row for snaptrash.voice_alerts table - logs triggered calls and outcomes."""
    alert_id: str
    zip: str
    neighborhood: str
    triggered_at: datetime
    plastic_volume_7day: float
    threshold: float
    report_context_json: str  # serialized PlasticReportContext
    call_id: str | None = None
    transcript: str | None = None
    status: str = "triggered"  # triggered, calling, completed, failed
    notified: bool = False
    ended_reason: str | None = None


class EmailAlertRow(BaseModel):
    """Row for snaptrash.email_alerts table (new for SMTP plastic alerts).
    Logs sent emails to hardcoded recipients (manasvinsurya.nitt02@gmail.com, mbj@ucsd.edu).
    Mirrors VoiceAlertRow but for email status. Used to prevent duplicate notifications."""
    alert_id: str
    zip: str
    neighborhood: str
    triggered_at: datetime
    plastic_volume_7day: float
    threshold: float
    report_context_json: str  # serialized PlasticReportContext
    sent_to: str  # comma-separated list of emails
    status: str = "sent"  # sent, failed, skipped
    notified: bool = True
    error: str | None = None
