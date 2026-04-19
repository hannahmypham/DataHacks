# Databricks notebook source
# MAGIC %md
# MAGIC # Prophet forecast — per restaurant
# MAGIC Schedule daily.

# COMMAND ----------
# MAGIC %pip install -q prophet

# COMMAND ----------
import sys
sys.path.insert(0, "/Volumes/workspace/analytics/pylib")

try:
    from snaptrash_analytics.forecasting.prophet_forecast import main
    main()
except ImportError as e:
    print(f"Import error (prophet not ready?): {e}")
    raise
except Exception as e:
    print(f"Forecast error: {e}")
    raise
