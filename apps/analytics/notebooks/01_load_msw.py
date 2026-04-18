# Databricks notebook source
# MAGIC %md
# MAGIC # Load Dryad MSW dataset → snaptrash.msw_baseline
# MAGIC Run on a Databricks cluster with internet access.

# COMMAND ----------
# MAGIC %pip install -q httpx pandas openpyxl

# COMMAND ----------
import sys
sys.path.insert(0, "/Workspace/Repos/<user>/SmartWaste/packages/common/src")
sys.path.insert(0, "/Workspace/Repos/<user>/SmartWaste/apps/analytics/src")

from snaptrash_analytics.ingest.load_msw_dryad import main
main()

# COMMAND ----------
# MAGIC %sql
# MAGIC SELECT COUNT(*), MIN(year), MAX(year) FROM workspace.snaptrash.msw_baseline;
