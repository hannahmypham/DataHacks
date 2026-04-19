"""
County-level Prophet forecast — trains on Dryad 2015-2019 SD disposal time series.
Produces forecast rows for the NEXT 3 years of SD disposal (tons/yr + per-capita kg).

This is the 'demo-day' forecast that works WITHOUT any CV scans. Used for:
  - Locality popup trend line
  - Baseline anchor for under-seeded per-restaurant Prophet models

Output: snaptrash.analytics.gold_sd_county_forecast
"""
from __future__ import annotations

import pandas as pd
import mlflow
from prophet import Prophet

from snaptrash_common.databricks_client import execute, fetch_all
from snaptrash_common.tables import GOLD_SD_DISPOSAL, GOLD_COUNTY_FCST

mlflow.set_experiment("/snaptrash/prophet_county")
try:
    mlflow.autolog(silent=True)
except Exception:
    pass

FORECAST_YEARS = 3


def _load_history() -> pd.DataFrame:
    """Most recent 5 years of SD county disposal — training window."""
    rows = fetch_all(f"""
        WITH maxy AS (SELECT MAX(year) AS m FROM {GOLD_SD_DISPOSAL})
        SELECT year, disposal_tons, disposal_per_capita_kg, population
        FROM {GOLD_SD_DISPOSAL}, maxy
        WHERE year > maxy.m - 5
        ORDER BY year
    """)
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["year"] = df["year"].astype(int)
    # Prophet needs datetime ds
    df["ds"] = pd.to_datetime(df["year"].astype(str) + "-01-01")
    df["disposal_tons"] = df["disposal_tons"].astype(float)
    df["disposal_per_capita_kg"] = df["disposal_per_capita_kg"].astype(float)
    df["population"] = df["population"].astype(int)
    return df


def _fit_and_forecast(df: pd.DataFrame, target_col: str) -> pd.DataFrame:
    """Fit Prophet on (ds, y=target_col), forecast FORECAST_YEARS ahead."""
    m = Prophet(
        yearly_seasonality=False,     # annual data, not enough periods
        weekly_seasonality=False,
        daily_seasonality=False,
        n_changepoints=1,             # only 5 obs
        seasonality_mode="additive",
    )
    fit_df = df[["ds", target_col]].rename(columns={target_col: "y"})
    m.fit(fit_df)
    future = m.make_future_dataframe(periods=FORECAST_YEARS, freq="YS")
    fc = m.predict(future)
    return fc[["ds", "yhat", "yhat_lower", "yhat_upper"]]


def main():
    df = _load_history()
    if df.empty:
        print("⚠️ No SD county history in gold_sd_disposal_ts — skip.")
        return 0

    print(f"Training on {len(df)} years: {df['year'].min()}–{df['year'].max()}")
    with mlflow.start_run(run_name="sd_county_disposal"):
        fc_tons = _fit_and_forecast(df, "disposal_tons")
        fc_tons = fc_tons.rename(columns={
            "yhat": "disposal_tons_fcst",
            "yhat_lower": "disposal_tons_lo",
            "yhat_upper": "disposal_tons_hi",
        })
        fc_pc = _fit_and_forecast(df, "disposal_per_capita_kg")
        fc_pc = fc_pc.rename(columns={
            "yhat": "per_capita_kg_fcst",
            "yhat_lower": "per_capita_kg_lo",
            "yhat_upper": "per_capita_kg_hi",
        })
        mlflow.log_metric("history_years", len(df))

    merged = fc_tons.merge(fc_pc, on="ds")
    merged["year"] = merged["ds"].dt.year
    merged["is_forecast"] = merged["year"] > df["year"].max()

    # Rebuild output table
    execute(f"DROP TABLE IF EXISTS {GOLD_COUNTY_FCST}")
    execute(f"""
        CREATE TABLE {GOLD_COUNTY_FCST} (
            year                INT,
            disposal_tons_fcst  DOUBLE,
            disposal_tons_lo    DOUBLE,
            disposal_tons_hi    DOUBLE,
            per_capita_kg_fcst  DOUBLE,
            per_capita_kg_lo    DOUBLE,
            per_capita_kg_hi    DOUBLE,
            is_forecast         BOOLEAN
        ) USING DELTA
    """)

    for _, r in merged.iterrows():
        execute(
            f"""INSERT INTO {GOLD_COUNTY_FCST} VALUES
                (:yr, :t, :tl, :th, :p, :pl, :ph, :f)""",
            {
                "yr": int(r["year"]),
                "t": float(r["disposal_tons_fcst"]),
                "tl": float(r["disposal_tons_lo"]),
                "th": float(r["disposal_tons_hi"]),
                "p": float(r["per_capita_kg_fcst"]),
                "pl": float(r["per_capita_kg_lo"]),
                "ph": float(r["per_capita_kg_hi"]),
                "f": bool(r["is_forecast"]),
            },
        )

    print(f"✅ gold_sd_county_forecast: {len(merged)} rows "
          f"(hist + {FORECAST_YEARS}y forecast)")
    for _, r in merged.iterrows():
        tag = " [fcst]" if r["is_forecast"] else ""
        print(f"  {int(r['year'])}: {r['disposal_tons_fcst']/1e6:.2f}M tons, "
              f"{r['per_capita_kg_fcst']:.0f} kg/person{tag}")
    return len(merged)


if __name__ == "__main__":
    main()
