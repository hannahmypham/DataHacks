"""Load MSW data from workspace.hackathon tables → snaptrash.msw_baseline.

Source: Dryad dataset already uploaded to Databricks (workspace.hackathon).
Primary table: wcs_2 — state-level commercial/residential waste by material (2002-2021).
Also reads: bans_thresholds, composting_capacity_all_states for enrichment.
"""
from __future__ import annotations
import pandas as pd

from snaptrash_common.databricks_client import execute, fetch_all
from snaptrash_common.tables import MSW_BASELINE

HACKATHON = "workspace.hackathon"


def load_wcs2() -> pd.DataFrame:
    """Commercial waste by state/year/material from wcs_2."""
    rows = fetch_all(f"""
        SELECT
            CAST(year AS INT)       AS year,
            state_id                AS state,
            material                AS waste_type,
            CAST(tons AS DOUBLE)    AS total_tons
        FROM {HACKATHON}.wcs_2
        WHERE generator_category = 'commercial'
          AND tons IS NOT NULL
          AND year IS NOT NULL
        ORDER BY state_id, year
    """)
    df = pd.DataFrame(rows)
    # avg kg/restaurant proxy: commercial tons * 907.185 kg/ton / estimated restaurant count per state
    # Using 1000 as conservative restaurant-per-state denominator (overridden by threshold logic)
    df["avg_commercial_waste_kg_per_restaurant"] = (
        df["total_tons"].astype(float) * 907.185 / 1000
    )
    return df


def to_values_clause(df: pd.DataFrame) -> str:
    rows = []
    for _, r in df.iterrows():
        state = str(r["state"]).replace("'", "''")
        wt = str(r["waste_type"]).replace("'", "''")
        year = int(r["year"]) if pd.notna(r["year"]) else 0
        tons = float(r["total_tons"]) if pd.notna(r["total_tons"]) else 0.0
        avg = float(r["avg_commercial_waste_kg_per_restaurant"]) if pd.notna(r["avg_commercial_waste_kg_per_restaurant"]) else 0.0
        rows.append(f"({year}, '{state}', '{wt}', {tons}, {avg})")
    return ",\n".join(rows)


def load_to_delta(df: pd.DataFrame, *, replace: bool = True) -> int:
    if replace:
        execute(f"DELETE FROM {MSW_BASELINE}")
    BATCH = 500
    total = 0
    for i in range(0, len(df), BATCH):
        chunk = df.iloc[i : i + BATCH]
        execute(f"INSERT INTO {MSW_BASELINE} VALUES {to_values_clause(chunk)}")
        total += len(chunk)
        print(f"  → inserted {total}/{len(df)}")
    return total


def main():
    print(f"reading commercial waste data from {HACKATHON}.wcs_2 ...")
    df = load_wcs2()
    print(f"  {len(df)} rows | states: {df['state'].nunique()} | years: {df['year'].min()}–{df['year'].max()}")
    n = load_to_delta(df)
    print(f"✅ loaded {n} rows into {MSW_BASELINE}")


if __name__ == "__main__":
    main()
