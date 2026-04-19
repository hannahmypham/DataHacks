"""
Single source of truth for Delta table names + DDL.
Both ingestion, analytics, and voice-alerts apps import from here.
DO NOT change column names without coordinating across apps (per snaptrash skill and plan).
Includes voice_alerts + new EMAIL_ALERTS for plastic threshold notifications (locality/restaurant).
"""
from .env import settings

SCANS = settings.fq_table("scans")
MSW_BASELINE = settings.fq_table("msw_baseline")
INSIGHTS = settings.fq_table("insights")
LOCALITY_AGG = settings.fq_table("locality_agg")
ENZYME_ALERTS = settings.fq_table("enzyme_alerts")
VOICE_ALERTS = settings.fq_table("voice_alerts")
EMAIL_ALERTS = settings.fq_table("email_alerts")
# Gold reference tables live in a SEPARATE analytics schema to keep
# the snaptrash namespace clean (CV team owns workspace.snaptrash).
_ANALYTICS_SCHEMA = f"{settings.DATABRICKS_CATALOG}.analytics"
GOLD_WCS            = f"{_ANALYTICS_SCHEMA}.gold_wcs_benchmark"
GOLD_SD_DISPOSAL    = f"{_ANALYTICS_SCHEMA}.gold_sd_disposal_ts"
GOLD_COMPOSTING     = f"{_ANALYTICS_SCHEMA}.gold_composting_routes_ca"
GOLD_CA_CAPACITY    = f"{_ANALYTICS_SCHEMA}.gold_ca_composting_capacity"
GOLD_SD_POPULATION  = f"{_ANALYTICS_SCHEMA}.gold_sd_population"
GOLD_SD_ZIP_POP     = f"{_ANALYTICS_SCHEMA}.gold_sd_zip_pop"
GOLD_SD_RESTAURANTS = f"{_ANALYTICS_SCHEMA}.gold_sd_restaurant_count"
GOLD_SD_COMMERCIAL  = f"{_ANALYTICS_SCHEMA}.gold_sd_commercial_benchmark"
GOLD_COUNTY_FCST    = f"{_ANALYTICS_SCHEMA}.gold_sd_county_forecast"
GOLD_FOOD_PRICES    = f"{_ANALYTICS_SCHEMA}.gold_food_prices"
GOLD_SHELF_LIFE     = f"{_ANALYTICS_SCHEMA}.gold_food_shelf_life"
# Synthetic scans for demo-day dev — real CV team writes to SCANS; we read UNION.
SYNTH_SCANS         = f"{_ANALYTICS_SCHEMA}.synthetic_scans"
SCANS_UNIFIED       = f"{_ANALYTICS_SCHEMA}.scans_unified"


def ddl_create_schema() -> str:
    return f"CREATE SCHEMA IF NOT EXISTS {settings.fq_schema}"


def ddl_scans() -> str:
    return f"""
    CREATE TABLE IF NOT EXISTS {SCANS} (
        scan_id STRING,
        restaurant_id STRING,
        zip STRING,
        neighborhood STRING,
        timestamp TIMESTAMP,
        food_kg DOUBLE,
        compostable_kg DOUBLE,
        contaminated_kg DOUBLE,
        dollar_wastage DOUBLE,
        co2_kg DOUBLE,
        plastic_count INT,
        harmful_plastic_count INT,
        pet_kg DOUBLE,
        ps_count INT,
        total_plastic_kg DOUBLE,
        ban_flag_count INT,
        recyclable_count INT,
        food_items_json STRING,
        plastic_items_json STRING
    ) USING DELTA
    PARTITIONED BY (zip)
    """


def ddl_msw_baseline() -> str:
    return f"""
    CREATE TABLE IF NOT EXISTS {MSW_BASELINE} (
        year INT,
        state STRING,
        waste_type STRING,
        total_tons DOUBLE,
        avg_commercial_waste_kg_per_restaurant DOUBLE
    ) USING DELTA
    """


def ddl_insights() -> str:
    """Extended insights: includes sustainability score, badge, locality popup, forecasts."""
    return f"""
    CREATE TABLE IF NOT EXISTS {INSIGHTS} (
        restaurant_id          STRING,
        computed_at            TIMESTAMP,
        -- locality context (carried from scans for GROUP BY zip / UI)
        zip                    STRING,
        neighborhood           STRING,
        -- rolling 7-day actuals
        weekly_food_kg         DOUBLE,
        weekly_dollar_waste    DOUBLE,
        weekly_plastic_count   INT,
        weekly_co2_kg          DOUBLE,
        compost_yield_rate     DOUBLE,   -- compostable_kg / food_kg
        contamination_rate     DOUBLE,   -- contaminated_kg / food_kg
        -- forecasts (from Prophet)
        forecast_food_kg       DOUBLE,   -- next 7d food waste kg
        forecast_dollar_waste  DOUBLE,   -- next 7d dollar wastage
        forecast_plastic_count INT,      -- next 7d plastic items
        -- WCS benchmark comparison
        wcs_food_pct_restaurant DOUBLE,  -- this restaurant's food% of total waste
        wcs_food_pct_ca_avg    DOUBLE,   -- CA commercial avg (17.7%)
        wcs_gap                DOUBLE,   -- positive = above CA avg (worse)
        -- composting
        nearest_facility_name           STRING,
        nearest_facility_km             DOUBLE,
        nearest_facility_capacity_tons  INT,
        ca_network_capacity_tons        INT,
        -- locality ranking (gamification)
        locality_percentile    DOUBLE,   -- 0–1, PERCENT_RANK()
        locality_percentile_pct INT,     -- 0–100 display value
        zip_restaurant_count   INT,
        better_than_count      INT,
        -- sustainability score (Person B 5-signal spec, equal 20% weights)
        sustainability_score   DOUBLE,   -- 1–4
        signal_1               DOUBLE,   -- food_vs_zip
        signal_2               DOUBLE,   -- banned+harmful plastics penalty
        signal_3               DOUBLE,   -- recyclability_rate
        signal_4               DOUBLE,   -- plastic_vs_zip
        signal_5               DOUBLE,   -- WoW reduction
        badge_tier             STRING,   -- Thriving Forest | Full Tree | Growing Plant | Small Sprout | Seed | Bare Root
        tier_emoji             STRING,   -- 🌳 🌲 🌿 🌱 🌰 🪨
        tier_key               STRING,   -- asset filename key (thriving_forest etc.)
        -- day-of-week insight
        peak_waste_day         STRING,   -- e.g. "Tuesday"
        peak_waste_day_kg      DOUBLE,
        -- pre-built display strings for frontend
        top_waste_category     STRING,
        recommendation         STRING,
        score_feedback_message STRING,   -- "Score: 84/100 · Gold. Better than 31 of 47..."
        co2_avoided            DOUBLE,
        -- shelf-life enrichment (USDA FoodKeeper + prepped_at from CV)
        shelf_life_min_days    DOUBLE,   -- most-urgent item across the week
        shelf_life_avg_days    DOUBLE,   -- kg-weighted average
        at_risk_kg_24h         DOUBLE    -- food kg with ≤1 day remaining
    ) USING DELTA
    """


def ddl_locality_agg() -> str:
    return f"""
    CREATE TABLE IF NOT EXISTS {LOCALITY_AGG} (
        zip                          STRING,
        neighborhood                 STRING,
        computed_at                  TIMESTAMP,
        -- plastic
        total_pet_kg                 DOUBLE,
        total_ps_count               INT,
        harmful_count                INT,
        -- restaurants
        active_restaurants           INT,
        -- food
        total_food_kg                DOUBLE,
        avg_food_kg_per_restaurant   DOUBLE,
        -- per-capita (uses population.csv SD data)
        food_waste_per_capita_kg     DOUBLE,
        -- vs SD county benchmark (from power2_impexp)
        sd_county_avg_disposal_kg    DOUBLE,
        pct_vs_sd_avg                DOUBLE,   -- (zip_per_cap / sd_avg) - 1, signed
        -- sustainability
        avg_sustainability_score     DOUBLE,
        -- enzyme
        enzyme_alert                 BOOLEAN
    ) USING DELTA
    """


def ddl_enzyme_alerts() -> str:
    return f"""
    CREATE TABLE IF NOT EXISTS {ENZYME_ALERTS} (
        alert_id        STRING,
        zip             STRING,
        neighborhood    STRING,
        triggered_at    TIMESTAMP,
        pet_volume_7day DOUBLE,
        threshold       DOUBLE,
        forecast_peak   DOUBLE,
        notified        BOOLEAN
    ) USING DELTA
    """


def ddl_voice_alerts() -> str:
    """Voice alerts for plastic volume >150kg/week. Logs calls, transcripts, and Vapi outcomes."""
    return f"""
    CREATE TABLE IF NOT EXISTS {VOICE_ALERTS} (
        alert_id             STRING,
        zip                  STRING,
        neighborhood         STRING,
        triggered_at         TIMESTAMP,
        plastic_volume_7day  DOUBLE,
        threshold            DOUBLE,
        report_context_json  STRING,
        call_id              STRING,
        transcript           STRING,
        status               STRING,
        notified             BOOLEAN,
        ended_reason         STRING
    ) USING DELTA
    PARTITIONED BY (zip)
    """


def ddl_email_alerts() -> str:
    """Email alerts for plastic thresholds (SMTP to hardcoded emails). Parallel to voice_alerts.
    Logs sent_to, status, error for deduplication and auditing (per plan)."""
    return f"""
    CREATE TABLE IF NOT EXISTS {EMAIL_ALERTS} (
        alert_id             STRING,
        zip                  STRING,
        neighborhood         STRING,
        triggered_at         TIMESTAMP,
        plastic_volume_7day  DOUBLE,
        threshold            DOUBLE,
        report_context_json  STRING,
        sent_to              STRING,
        status               STRING,
        notified             BOOLEAN,
        error                STRING
    ) USING DELTA
    PARTITIONED BY (zip)
    """


def ddl_gold_wcs_benchmark() -> str:
    """CA commercial waste % by material — the benchmark every restaurant is scored against."""
    return f"""
    CREATE TABLE IF NOT EXISTS {GOLD_WCS} (
        material        STRING,
        year            INT,
        tons            DOUBLE,
        state_total_tons DOUBLE,
        material_pct    DOUBLE    -- % this material is of total CA commercial waste
    ) USING DELTA
    """


def ddl_gold_sd_disposal_ts() -> str:
    """SD county per-capita disposal time series 2015-2019 (trend line for map + context)."""
    return f"""
    CREATE TABLE IF NOT EXISTS {GOLD_SD_DISPOSAL} (
        year                      INT,
        county                    STRING,
        disposal_tons             DOUBLE,
        population                INT,
        disposal_per_capita_kg    DOUBLE
    ) USING DELTA
    """


def ddl_gold_composting_routes_ca() -> str:
    """CA composting facilities sorted by distance from SD center."""
    return f"""
    CREATE TABLE IF NOT EXISTS {GOLD_COMPOSTING} (
        facility_name          STRING,
        lat                    DOUBLE,
        lng                    DOUBLE,
        capacity_tons          DOUBLE,
        dist_from_sd_center_km DOUBLE
    ) USING DELTA
    """


def ddl_scans_unified() -> str:
    """
    UNION ALL view that makes analytics pipelines agnostic to whether data
    comes from the real CV-owned SCANS table or dev-only SYNTH_SCANS.
    Rebuild whenever either source's schema changes.
    """
    return f"""
    CREATE OR REPLACE VIEW {SCANS_UNIFIED} AS
    SELECT
        scan_id, restaurant_id, zip, neighborhood, timestamp,
        food_kg, compostable_kg, contaminated_kg,
        dollar_wastage, co2_kg,
        plastic_count, harmful_plastic_count, pet_kg, ps_count,
        total_plastic_kg, ban_flag_count, recyclable_count,
        food_items_json, plastic_items_json,
        FALSE AS is_synthetic
    FROM {SCANS}
    UNION ALL
    SELECT
        scan_id, restaurant_id, zip, neighborhood, timestamp,
        food_kg, compostable_kg, contaminated_kg,
        dollar_wastage, co2_kg,
        plastic_count, harmful_plastic_count, pet_kg, ps_count,
        total_plastic_kg, ban_flag_count, recyclable_count,
        food_items_json, plastic_items_json,
        TRUE  AS is_synthetic
    FROM {SYNTH_SCANS}
    """


ALL_DDL = [
    ddl_scans,
    ddl_msw_baseline,
    ddl_insights,
    ddl_locality_agg,
    ddl_enzyme_alerts,
    ddl_voice_alerts,
    ddl_email_alerts,
    ddl_gold_wcs_benchmark,
    ddl_gold_sd_disposal_ts,
    ddl_gold_composting_routes_ca,
    # ddl_scans_unified runs last — depends on SCANS + SYNTH_SCANS existing.
    # bootstrap_databricks.py skips this if SYNTH_SCANS not yet seeded.
    ddl_scans_unified,
]
