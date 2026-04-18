# Databricks notebook source
# MAGIC %md
# MAGIC # Hourly aggregations
# MAGIC Schedule via Databricks Workflows: every 1 hour.

# COMMAND ----------
import sys
sys.path.insert(0, "/Workspace/Repos/<user>/SmartWaste/packages/common/src")
sys.path.insert(0, "/Workspace/Repos/<user>/SmartWaste/apps/analytics/src")

from snaptrash_analytics.aggregations import locality_agg, restaurant_rolling, threshold_check

locality_agg.main()
restaurant_rolling.main()
threshold_check.main()
