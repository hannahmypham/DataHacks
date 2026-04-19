# Databricks notebook source
# MAGIC %md
# MAGIC # Prophet forecast — per restaurant
# MAGIC Schedule daily.

# COMMAND ----------
# Install prophet only if not already available (avoids 2-3 min reinstall on warm clusters)
try:
    import prophet  # noqa: F401
    print("prophet already installed — skipping pip install")
except ImportError:
    import subprocess, sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "prophet"])
    print("prophet installed")

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
