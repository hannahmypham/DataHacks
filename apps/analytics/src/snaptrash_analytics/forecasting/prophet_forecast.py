"""
Per-restaurant Prophet forecasts — run daily.

Forecasts 3 targets per restaurant:
  1. food_kg        → forecast_food_kg  (next 7 days)
  2. dollar_wastage → forecast_dollar_waste
  3. plastic_count  → forecast_plastic_count

Uses SD county disposal time series (gold_sd_disposal_ts) as an external
regressor to anchor forecasts for new restaurants with <14 days of data.

MLflow autolog enabled — each run tracked per restaurant.
"""
from __future__ import annotations
from datetime import datetime, timezone

import pandas as pd
from prophet import Prophet

from snaptrash_common.databricks_client import execute, fetch_all
from snaptrash_common.tables import SCANS_UNIFIED, INSIGHTS, GOLD_SD_DISPOSAL

# MLflow is optional — pre-installed on some Databricks runtimes, absent on others.
try:
    import mlflow
    _MLFLOW = True
except ImportError:
    mlflow = None
    _MLFLOW = False


def _setup_mlflow():
    if not _MLFLOW:
        print("  MLflow not available — skipping experiment tracking")
        return
    for exp_name in ("/Shared/snaptrash/prophet_v2", "/Users/ara023@ucsd.edu/snaptrash/prophet_v2"):
        try:
            mlflow.set_experiment(exp_name)
            break
        except Exception:
            try:
                exp_id = mlflow.create_experiment(exp_name)
                mlflow.set_experiment(experiment_id=exp_id)
                break
            except Exception:
                continue
    else:
        print("  MLflow experiment setup failed — continuing without tracking")
    try:
        mlflow.autolog(silent=True)
    except Exception:
        pass

_setup_mlflow()


class _nullctx:
    """No-op context manager used when MLflow is unavailable."""
    def __enter__(self): return self
    def __exit__(self, *_): pass


MIN_DAYS_FOR_PROPHET = 7  # use mean fallback below this

# ---------------------------------------------------------------------------
# Load SD county disposal trend as external regressor
# ---------------------------------------------------------------------------

def _load_sd_trend() -> dict[int, float]:
    """
    Returns {year: normalized_disposal_per_capita} for use as seasonal anchor.
    Normalized 0–1 across 2015–2019 range.
    """
    try:
        rows = fetch_all(
            f"SELECT year, disposal_per_capita_kg FROM {GOLD_SD_DISPOSAL} ORDER BY year"
        )
        if not rows:
            return {}
        vals = {int(r["year"]): float(r["disposal_per_capita_kg"]) for r in rows}
        min_v, max_v = min(vals.values()), max(vals.values())
        rng = max_v - min_v or 1
        return {yr: (v - min_v) / rng for yr, v in vals.items()}
    except Exception:
        return {}


def _sd_regressor_value(ds: pd.Timestamp, sd_trend: dict) -> float:
    """Interpolate SD trend for a given date by year."""
    if not sd_trend:
        return 0.5
    yr = ds.year
    # Clamp to known range
    years = sorted(sd_trend.keys())
    if yr <= years[0]:
        return sd_trend[years[0]]
    if yr >= years[-1]:
        return sd_trend[years[-1]]
    # Linear interpolation between adjacent years
    for i in range(len(years) - 1):
        if years[i] <= yr <= years[i + 1]:
            frac = (yr - years[i]) / (years[i + 1] - years[i])
            return sd_trend[years[i]] + frac * (sd_trend[years[i + 1]] - sd_trend[years[i]])
    return 0.5


# ---------------------------------------------------------------------------
# Fit + predict one time series
# ---------------------------------------------------------------------------

def _fit_forecast(df: pd.DataFrame, target: str,
                  sd_trend: dict, use_regressor: bool = True) -> float:
    """
    Fit Prophet on df[['ds', target]] and return sum of 7-day forecast.
    df must have columns: ds (datetime), {target} (float).
    Returns 0.0 if not enough data.
    """
    sub = df[["ds", target]].rename(columns={target: "y"}).dropna()
    sub = sub[sub["y"] >= 0]

    if len(sub) < MIN_DAYS_FOR_PROPHET:
        # Not enough history — return 7× daily mean
        return float(sub["y"].mean()) * 7 if len(sub) > 0 else 0.0

    m = Prophet(
        weekly_seasonality=True,
        daily_seasonality=False,
        yearly_seasonality=False,
        changepoint_prior_scale=0.1,  # less aggressive for short series
    )

    if use_regressor and sd_trend:
        m.add_regressor("sd_county_trend")
        sub = sub.copy()
        sub["sd_county_trend"] = sub["ds"].apply(
            lambda d: _sd_regressor_value(d, sd_trend)
        )

    m.fit(sub)
    future = m.make_future_dataframe(periods=7)

    if use_regressor and sd_trend:
        future["sd_county_trend"] = future["ds"].apply(
            lambda d: _sd_regressor_value(d, sd_trend)
        )

    fc = m.predict(future)
    next_7d = fc.tail(7)["yhat"].clip(lower=0).sum()
    return float(next_7d)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    sd_trend = _load_sd_trend()
    print(f"SD disposal trend loaded: {len(sd_trend)} years "
          f"({min(sd_trend) if sd_trend else 'N/A'}–{max(sd_trend) if sd_trend else 'N/A'})")

    # Pull 60 days of daily scan data per restaurant
    rows = fetch_all(f"""
        SELECT
          restaurant_id,
          date_trunc('day', timestamp)  AS ds,
          SUM(food_kg)                   AS food_kg,
          SUM(dollar_wastage)            AS dollar_wastage,
          SUM(plastic_count)             AS plastic_count
        FROM {SCANS_UNIFIED}
        WHERE timestamp >= NOW() - INTERVAL 60 DAYS
        GROUP BY restaurant_id, date_trunc('day', timestamp)
        ORDER BY restaurant_id, ds
    """)

    if not rows:
        print("No scan data — nothing to forecast.")
        return

    df = pd.DataFrame(rows)
    df["ds"] = pd.to_datetime(df["ds"])
    df["food_kg"] = pd.to_numeric(df["food_kg"], errors="coerce").fillna(0)
    df["dollar_wastage"] = pd.to_numeric(df["dollar_wastage"], errors="coerce").fillna(0)
    df["plastic_count"] = pd.to_numeric(df["plastic_count"], errors="coerce").fillna(0)

    now = datetime.now(timezone.utc).isoformat()
    restaurants = df["restaurant_id"].unique()
    print(f"Forecasting {len(restaurants)} restaurants...")

    for rid in restaurants:
        sub = df[df["restaurant_id"] == rid].copy().sort_values("ds")

        _run_ctx = mlflow.start_run(run_name=f"forecast_{rid}") if _MLFLOW else _nullctx()
        with _run_ctx:
            food_7d = _fit_forecast(sub, "food_kg", sd_trend)
            dollar_7d = _fit_forecast(sub, "dollar_wastage", sd_trend)
            plastic_7d = _fit_forecast(sub, "plastic_count", sd_trend, use_regressor=False)

            if _MLFLOW:
                mlflow.log_params({
                    "restaurant_id": rid,
                    "training_days": len(sub),
                    "sd_trend_years": len(sd_trend),
                })
                mlflow.log_metrics({
                    "forecast_food_kg_7d": food_7d,
                    "forecast_dollar_waste_7d": dollar_7d,
                    "forecast_plastic_7d": plastic_7d,
                })

            # Forecast insight message
            last_food = float(sub["food_kg"].tail(7).sum())
            delta_pct = ((food_7d - last_food) / max(last_food, 0.001)) * 100
            direction = "above" if delta_pct > 0 else "below"
            forecast_rec = (
                f"Forecast next 7 days: {food_7d:.1f} kg food waste "
                f"({abs(delta_pct):.0f}% {direction} last week). "
                f"Projected wastage: ${dollar_7d:.0f}."
            )
            if food_7d > last_food * 1.15:
                forecast_rec += " Consider reducing orders this week."

            # Update insights row with forecasts
            execute(f"""
                UPDATE {INSIGHTS}
                SET
                  forecast_food_kg       = :food,
                  forecast_dollar_waste  = :dollar,
                  forecast_plastic_count = :plastic,
                  recommendation         = CONCAT(recommendation, ' | ', :fc_rec)
                WHERE restaurant_id = :rid
                  AND computed_at = (
                    SELECT MAX(computed_at) FROM {INSIGHTS}
                    WHERE restaurant_id = :rid
                  )
            """, {
                "food": round(food_7d, 2),
                "dollar": round(dollar_7d, 2),
                "plastic": int(plastic_7d),
                "fc_rec": forecast_rec,
                "rid": rid,
            })

            print(
                f"  {rid[:20]:20s} | food: {food_7d:6.1f} kg "
                f"| ${dollar_7d:6.0f} | plastic: {int(plastic_7d):4d}"
            )

    print(f"✅ Forecasts complete for {len(restaurants)} restaurants.")


if __name__ == "__main__":
    main()
