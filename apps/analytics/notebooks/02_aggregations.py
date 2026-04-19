# Databricks notebook source
# MAGIC %md
# MAGIC # Hourly Aggregations
# MAGIC Schedule via Databricks Workflows: every 1 hour.
# MAGIC
# MAGIC Run order:
# MAGIC 1. restaurant_rolling   → 7-day totals + WCS gap + day-of-week insight
# MAGIC 2. sustainability_score → score + badge + percentile + locality popup
# MAGIC 3. locality_agg         → per-ZIP aggregates + per-capita vs SD avg
# MAGIC 4. threshold_check      → enzyme alert detection

# COMMAND ----------
import sys
sys.path.insert(0, "/Volumes/workspace/analytics/pylib")

# Step 1: Restaurant 7-day rolling aggregation
from snaptrash_analytics.aggregations.restaurant_rolling import main as rolling_main
rolling_main()

# Step 2: Sustainability score + badge + locality ranking
from snaptrash_analytics.aggregations.sustainability_score import main as score_main
score_main()

# Step 3: Locality ZIP aggregation
from snaptrash_analytics.aggregations.locality_agg import main as locality_main
locality_main()

# Step 4: Threshold + enzyme alert detection
from snaptrash_analytics.aggregations.threshold_check import main as threshold_main
threshold_main()

# COMMAND ----------
# MAGIC %sql
# MAGIC -- Spot-check latest insights (incl. shelf-life enrichment)
# MAGIC SELECT restaurant_id, zip, neighborhood,
# MAGIC        ROUND(sustainability_score, 1) AS score,
# MAGIC        tier_emoji, badge_tier, tier_key,
# MAGIC        ROUND(signal_1, 1) AS s1_food_vs_zip,
# MAGIC        ROUND(signal_2, 1) AS s2_banned_plastic,
# MAGIC        ROUND(signal_3, 1) AS s3_recyclable,
# MAGIC        ROUND(signal_4, 1) AS s4_plastic_vs_zip,
# MAGIC        ROUND(signal_5, 1) AS s5_wow,
# MAGIC        better_than_count, zip_restaurant_count,
# MAGIC        shelf_life_min_days, at_risk_kg_24h,
# MAGIC        score_feedback_message
# MAGIC FROM workspace.snaptrash.insights
# MAGIC WHERE computed_at >= NOW() - INTERVAL 2 HOURS
# MAGIC ORDER BY sustainability_score DESC
# MAGIC LIMIT 20;

# COMMAND ----------
# MAGIC %sql
# MAGIC -- Locality overview
# MAGIC SELECT zip, neighborhood,
# MAGIC        active_restaurants,
# MAGIC        ROUND(avg_sustainability_score, 1) AS avg_score,
# MAGIC        ROUND(food_waste_per_capita_kg, 3) AS food_kg_per_capita,
# MAGIC        ROUND(pct_vs_sd_avg * 100, 1) AS pct_vs_sd_county,
# MAGIC        enzyme_alert
# MAGIC FROM workspace.snaptrash.locality_agg
# MAGIC WHERE computed_at >= NOW() - INTERVAL 2 HOURS
# MAGIC ORDER BY avg_sustainability_score DESC;
