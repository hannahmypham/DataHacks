# Databricks notebook source
# MAGIC %md
# MAGIC # Load Gold Reference Tables (Dryad + Census)
# MAGIC Run ONCE at hackathon start. Reads from workspace.hackathon (Dryad) + Census public APIs.
# MAGIC Produces in workspace.analytics:
# MAGIC - gold_wcs_benchmark              (CA commercial waste % by material)
# MAGIC - gold_sd_population              (SD county pop 2015-2019, long format)
# MAGIC - gold_sd_disposal_ts             (SD county per-capita disposal 2015-2019)
# MAGIC - gold_composting_routes_ca       (CA composting facilities + capacity + km from SD)
# MAGIC - gold_ca_composting_capacity     (statewide CA capacity tons/yr)
# MAGIC - gold_sd_commercial_benchmark    (SD disposal × CA commercial % → tons per material)
# MAGIC - gold_sd_zip_pop                 (Census ACS per-ZIP pop)
# MAGIC - gold_sd_restaurant_count        (Census ZBP NAICS 722 per ZIP)
# MAGIC - gold_food_prices                (USDA ERS $/kg — dollar fallback)
# MAGIC - gold_food_shelf_life            (USDA FoodKeeper days — shelf-life fallback)
# MAGIC - scans_unified (VIEW)            (UNION ALL of scans + synthetic_scans)

# COMMAND ----------
# MAGIC %pip install -q databricks-sdk
# MAGIC dbutils.library.restartPython()

# COMMAND ----------
import sys
sys.path.insert(0, "/Volumes/workspace/analytics/pylib")

# Dryad-derived gold tables
from snaptrash_analytics.ingest.load_gold_tables import main as load_dryad
load_dryad()

# COMMAND ----------
# Census-derived gold tables (per-ZIP pop + restaurant counts)
from snaptrash_analytics.ingest.load_census_data import main as load_census
load_census()

# COMMAND ----------
# USDA price + shelf-life reference tables
from snaptrash_analytics.ingest.load_food_prices import main as load_prices
load_prices()
from snaptrash_analytics.ingest.load_shelf_life import main as load_shelf
load_shelf()

# COMMAND ----------
# Synthetic scans (demo-day only — CV team overwrites with real data)
from snaptrash_analytics.dev.seed_synthetic_scans import main as seed_synth
seed_synth()

# COMMAND ----------
# Unified view — aggregations read this instead of raw scans
from snaptrash_common.databricks_client import execute
from snaptrash_common.tables import ddl_scans_unified, INSIGHTS
execute(ddl_scans_unified())
print("✅ scans_unified view created (UNION ALL of scans + synthetic_scans)")

# COMMAND ----------
# Idempotent migration: add v2/v3 columns to insights if table existed earlier.
# v2: zip/neighborhood + shelf-life. v3: Person B 5-signal score + tier display.
for col, typ in [
    ("zip",                 "STRING"),
    ("neighborhood",        "STRING"),
    ("shelf_life_min_days", "DOUBLE"),
    ("shelf_life_avg_days", "DOUBLE"),
    ("at_risk_kg_24h",      "DOUBLE"),
    ("signal_1",            "DOUBLE"),
    ("signal_2",            "DOUBLE"),
    ("signal_3",            "DOUBLE"),
    ("signal_4",            "DOUBLE"),
    ("signal_5",            "DOUBLE"),
    ("tier_emoji",          "STRING"),
    ("tier_key",            "STRING"),
]:
    try:
        execute(f"ALTER TABLE {INSIGHTS} ADD COLUMN {col} {typ}")
        print(f"  + {col} {typ}")
    except Exception as e:
        msg = str(e).lower()
        if "already exists" in msg or "duplicate" in msg:
            print(f"  ✓ {col} already present")
        else:
            print(f"  · {col}: {e}")

# COMMAND ----------
# MAGIC %sql
# MAGIC SELECT 'WCS Benchmark'      AS table_, COUNT(*) AS rows FROM workspace.analytics.gold_wcs_benchmark
# MAGIC UNION ALL SELECT 'SD Population',        COUNT(*) FROM workspace.analytics.gold_sd_population
# MAGIC UNION ALL SELECT 'SD Disposal TS',       COUNT(*) FROM workspace.analytics.gold_sd_disposal_ts
# MAGIC UNION ALL SELECT 'Composting Routes',    COUNT(*) FROM workspace.analytics.gold_composting_routes_ca
# MAGIC UNION ALL SELECT 'CA Composting Cap',    COUNT(*) FROM workspace.analytics.gold_ca_composting_capacity
# MAGIC UNION ALL SELECT 'SD Commercial Bench',  COUNT(*) FROM workspace.analytics.gold_sd_commercial_benchmark
# MAGIC UNION ALL SELECT 'SD ZIP Pop (Census)',  COUNT(*) FROM workspace.analytics.gold_sd_zip_pop
# MAGIC UNION ALL SELECT 'SD Restaurant Cnt',    COUNT(*) FROM workspace.analytics.gold_sd_restaurant_count
# MAGIC UNION ALL SELECT 'Food Prices (USDA)',   COUNT(*) FROM workspace.analytics.gold_food_prices
# MAGIC UNION ALL SELECT 'Shelf Life (USDA)',    COUNT(*) FROM workspace.analytics.gold_food_shelf_life
# MAGIC UNION ALL SELECT 'Synthetic Scans',      COUNT(*) FROM workspace.analytics.synthetic_scans
# MAGIC UNION ALL SELECT 'Scans Unified (view)', COUNT(*) FROM workspace.analytics.scans_unified;

# COMMAND ----------
# MAGIC %sql
# MAGIC -- Typical SD restaurant weekly food waste baseline (derived)
# MAGIC SELECT
# MAGIC   SUM(sd_commercial_tons) AS sd_food_tons_yr,
# MAGIC   (SELECT SUM(restaurant_count) FROM workspace.analytics.gold_sd_restaurant_count) AS sd_restaurants,
# MAGIC   ROUND(SUM(sd_commercial_tons) * 907.185
# MAGIC         / (SELECT SUM(restaurant_count) FROM workspace.analytics.gold_sd_restaurant_count)
# MAGIC         / 52.0, 1) AS kg_per_restaurant_per_week
# MAGIC FROM workspace.analytics.gold_sd_commercial_benchmark
# MAGIC WHERE LOWER(material) = 'food';
