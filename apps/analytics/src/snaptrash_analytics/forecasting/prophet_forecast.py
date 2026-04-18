"""Per-restaurant 7-day Prophet forecast → snaptrash.insights.

MLflow autolog enabled. Run as one-off or from Databricks Workflow.
"""
from __future__ import annotations
from datetime import datetime, timezone
import pandas as pd
import mlflow
from prophet import Prophet

from snaptrash_common.databricks_client import execute, fetch_all
from snaptrash_common.tables import SCANS, INSIGHTS

mlflow.set_experiment("/snaptrash/prophet")
try:
    mlflow.autolog(silent=True)
except Exception:
    pass


SQL_DAILY = f"""
SELECT
  restaurant_id,
  date_trunc('day', timestamp) AS ds,
  SUM(food_kg) AS y
FROM {SCANS}
WHERE timestamp >= now() - INTERVAL 60 DAYS
GROUP BY restaurant_id, date_trunc('day', timestamp)
ORDER BY restaurant_id, ds
"""

INSERT_INSIGHT = f"""
INSERT INTO {INSIGHTS} VALUES (
  :restaurant_id, :computed_at, 0.0, :forecast, 0.0, 'food', :rec, 0.0
)
"""


def fit_one(df: pd.DataFrame) -> float:
    if len(df) < 7:
        return float(df["y"].mean()) * 7 if len(df) else 0.0
    m = Prophet(daily_seasonality=False, weekly_seasonality=True, yearly_seasonality=False)
    m.fit(df.rename(columns={"ds": "ds", "y": "y"}))
    future = m.make_future_dataframe(periods=7)
    fc = m.predict(future)
    return float(fc.tail(7)["yhat"].sum())


def main():
    rows = fetch_all(SQL_DAILY)
    if not rows:
        print("no scans yet — nothing to forecast")
        return
    df = pd.DataFrame(rows)
    df["ds"] = pd.to_datetime(df["ds"])
    df["y"] = pd.to_numeric(df["y"])
    now = datetime.now(timezone.utc).isoformat()

    for rid, sub in df.groupby("restaurant_id"):
        with mlflow.start_run(run_name=f"forecast_{rid}"):
            yhat_7d = fit_one(sub[["ds", "y"]].copy())
            mlflow.log_metric("forecast_next_week_kg", yhat_7d)
            mlflow.log_param("restaurant_id", rid)
            rec = (
                f"Forecast next 7d: {yhat_7d:.1f}kg food waste — "
                + ("trim portions" if yhat_7d > 50 else "on track")
            )
            execute(
                INSERT_INSIGHT,
                {"restaurant_id": rid, "computed_at": now, "forecast": yhat_7d, "rec": rec},
            )
    print(f"✅ forecast complete for {df['restaurant_id'].nunique()} restaurants")


if __name__ == "__main__":
    main()
