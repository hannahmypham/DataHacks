"""
Single source of truth for Delta table names + DDL.
Both ingestion and analytics apps import from here.
DO NOT change column names without coordinating across both apps.
"""
from .env import settings


SCANS = settings.fq_table("scans")
MSW_BASELINE = settings.fq_table("msw_baseline")
INSIGHTS = settings.fq_table("insights")
LOCALITY_AGG = settings.fq_table("locality_agg")
ENZYME_ALERTS = settings.fq_table("enzyme_alerts")


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
        food_items_json STRING,
        plastic_items_json STRING
    ) USING DELTA
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
    return f"""
    CREATE TABLE IF NOT EXISTS {INSIGHTS} (
        restaurant_id STRING,
        computed_at TIMESTAMP,
        weekly_dollar_waste DOUBLE,
        forecast_next_week DOUBLE,
        locality_percentile DOUBLE,
        top_waste_category STRING,
        recommendation STRING,
        co2_avoided DOUBLE
    ) USING DELTA
    """


def ddl_locality_agg() -> str:
    return f"""
    CREATE TABLE IF NOT EXISTS {LOCALITY_AGG} (
        zip STRING,
        neighborhood STRING,
        computed_at TIMESTAMP,
        total_pet_kg DOUBLE,
        total_ps_count INT,
        harmful_count INT,
        active_restaurants INT,
        enzyme_alert BOOLEAN
    ) USING DELTA
    """


def ddl_enzyme_alerts() -> str:
    return f"""
    CREATE TABLE IF NOT EXISTS {ENZYME_ALERTS} (
        alert_id STRING,
        zip STRING,
        neighborhood STRING,
        triggered_at TIMESTAMP,
        pet_volume_7day DOUBLE,
        threshold DOUBLE,
        forecast_peak DOUBLE,
        notified BOOLEAN
    ) USING DELTA
    """


ALL_DDL = [
    ddl_scans,
    ddl_msw_baseline,
    ddl_insights,
    ddl_locality_agg,
    ddl_enzyme_alerts,
]
