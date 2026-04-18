# Analytics App (Person B)

Stage 6 of SnapTrash pipeline:

- Load Dryad US Municipal Solid Waste dataset → `snaptrash.msw_baseline`
- Firecrawl: EPA banned plastics, BioCycle compost dirs, enzyme labs → `data/*.json`
- SQL aggregations (rolling 7-day, locality)
- Prophet forecast per restaurant (MLflow tracked)
- Threshold detection → `snaptrash.enzyme_alerts`

## Run

```bash
uv sync

# 1. Bootstrap tables (once)
cd ../.. && uv run --project apps/analytics python scripts/bootstrap_databricks.py

# 2. Load MSW dataset
uv run --project apps/analytics python -m snaptrash_analytics.ingest.load_msw_dryad

# 3. Firecrawl jobs (once at hour 1)
uv run --project apps/analytics python -m snaptrash_analytics.ingest.firecrawl_jobs

# 4. Aggregations (cron / manual)
uv run --project apps/analytics python -m snaptrash_analytics.aggregations.locality_agg
uv run --project apps/analytics python -m snaptrash_analytics.aggregations.restaurant_rolling
uv run --project apps/analytics python -m snaptrash_analytics.aggregations.threshold_check

# 5. Prophet forecast
uv run --project apps/analytics python -m snaptrash_analytics.forecasting.prophet_forecast
```

Notebooks in `notebooks/` are jupytext-paired `.py` files — sync them to Databricks via Workspace UI or Repos.

## Integration handoff

- Reads `snaptrash.scans` (written by Person A)
- Writes `snaptrash.insights`, `snaptrash.locality_agg`, `snaptrash.enzyme_alerts`
- Exposes `readers.insights_reader` query funcs — used by ingestion app's API in integration phase.
