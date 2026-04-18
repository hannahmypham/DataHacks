# Databricks notebook source
# MAGIC %md
# MAGIC # Prophet forecast — per restaurant
# MAGIC Schedule daily.

# COMMAND ----------
# MAGIC %pip install -q prophet mlflow

# COMMAND ----------
import sys
sys.path.insert(0, "/Workspace/Repos/<user>/SmartWaste/packages/common/src")
sys.path.insert(0, "/Workspace/Repos/<user>/SmartWaste/apps/analytics/src")

from snaptrash_analytics.forecasting.prophet_forecast import main
main()
