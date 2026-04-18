---
name: databricks-snaptrash
description: Databricks operations customized for the SnapTrash project (Delta Lake tables, SQL aggregations, Prophet forecasting, bootstrap scripts, MCP integration, analytics jobs). Combines global databricks skill with project-specific schemas from packages/common, ingestion/analytics split, MSW dataset loading, threshold detection for enzyme alerts, and the updated architecture (no barcode/manufacturer features). Use for all Databricks CLI, SDK, SQL, MLflow, notebooks, or when working on apps/analytics/, scripts/bootstrap_databricks.py, or tables.py.
---

# Databricks for SnapTrash

This skill adapts the global Databricks skill for the SnapTrash waste analytics project. Always combine with the `snaptrash` and `snaptrash-core` rules.

## Project-Specific Context

- **Catalog/Schema**: `workspace.snaptrash` (or per `settings.fq_schema` from `snaptrash_common.env`).
- **Core Tables** (defined in `packages/common/src/snaptrash_common/tables.py` and created by `scripts/bootstrap_databricks.py`):
  - `snaptrash.scans` (raw enriched scans from ingestion — **do not modify schema**).
  - `snaptrash.msw_baseline` (US Municipal Solid Waste Dryad dataset for thresholds/benchmarks).
  - `snaptrash.insights`, `snaptrash.locality_agg`, `snaptrash.enzyme_alerts` (computed by analytics jobs).
- **Workflow**:
  - Ingestion (`apps/ingestion/`) writes only to `scans`.
  - Analytics (`apps/analytics/`) reads `scans` + baseline, runs aggregations (`locality_agg.py`, `restaurant_rolling.py`), Prophet forecasts (`prophet_forecast.py`), threshold checks.
  - Use `databricks experimental aitools` for exploration as per global skill.
  - Notebooks in `apps/analytics/notebooks/` (load_msw, aggregations, forecast) sync to Databricks Repos.
- **MCP Integration**: The Databricks MCP server is configured — use it for live queries on Delta tables.

## Key Commands (SnapTrash Context)

Use `--profile` or env vars from `.env` (DATABRICKS_HOST/TOKEN/WAREHOUSE_ID). Never assume profile.

```bash
# Bootstrap (run once)
uv run --project apps/analytics python scripts/bootstrap_databricks.py

# Load reference data
uv run --project apps/analytics python -m snaptrash_analytics.ingest.load_msw_dryad
uv run --project apps/analytics python -m snaptrash_analytics.ingest.firecrawl_jobs

# Run analytics (hourly jobs)
uv run --project apps/analytics python -m snaptrash_analytics.aggregations.locality_agg
uv run --project apps/analytics python -m snaptrash_analytics.forecasting.prophet_forecast
uv run --project apps/analytics python -m snaptrash_analytics.aggregations.threshold_check

# Explore (use aitools as per global databricks skill)
databricks experimental aitools tools discover-schema workspace.snaptrash.scans
databricks experimental aitools tools query "SELECT * FROM workspace.snaptrash.locality_agg LIMIT 5" --profile snaptrash
```

## Rules for This Project
- **Always** use models from `snaptrash_common.schemas` (ScanRow, InsightRow, etc. — no manufacturer fields).
- Prophet models tracked in MLflow; forecasts written back to `insights`.
- Thresholds based on MSW baseline for enzyme alerts (PET volume, locality).
- When modifying tables, update both `tables.py`, bootstrap script, and `DETAILED-OVERVIEW.md`.
- For AWS S3 (images): Use the S3 client in `ingestion/services/s3_client.py` with credentials from `.env`. Bucket: `snaptrash-bins`.
- Follow global Databricks skill for CLI auth, profiles, Unity Catalog, bundles, etc., but prioritize project scripts over raw CLI for consistency.

## Common Tasks
- **Adding a new metric**: Update `ScanRow`/`InsightRow`, aggregation queries, reader, frontend, and overview docs.
- **Debugging pipeline**: Use MCP Databricks tool to query tables, check `enzyme_alerts`, verify Prophet RMSE in MLflow.
- **Scaling**: Convert notebooks to Databricks Workflows for hourly runs.

Combine with `firecrawl-snaptrash` for scraping reference data and `ui-ux-snaptrash` for any dashboard changes. See `snaptrash-plan.md` Stages 5-6 and `apps/analytics/README.md` for details.

This skill ensures Databricks work in SnapTrash is consistent, uses the shared common package, and respects the simplified architecture.
