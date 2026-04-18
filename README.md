# SnapTrash

Restaurant waste vision + analytics. See `snaptrash-plan.md` for full architecture.

## Repo Layout

```
SmartWaste/
├── apps/
│   ├── ingestion/    # Person A — S3 + Groq Vision + FastAPI + Delta writes (Stages 1-5)
│   ├── analytics/    # Person B — MSW load + SQL agg + Prophet + thresholds (Stage 6)
│   └── frontend/     # Vite + React + TS + Tailwind dashboard (later)
├── packages/
│   └── common/       # shared lib — Databricks client, schemas, table DDL
├── scripts/          # bootstrap_databricks, seed_fake_scans, run_dev
├── notebooks/        # Databricks notebooks (analytics app)
└── data/             # gitignored — Dryad CSV, scraped JSON
```

## Integration Contract

The **only coupling** between Person A and Person B is the Delta tables defined in
`packages/common/src/snaptrash_common/tables.py` and pydantic models in `schemas.py`.

| Person | Writes to | Reads from |
|---|---|---|
| A (ingestion) | `snaptrash.scans` | — |
| B (analytics) | `snaptrash.insights`, `snaptrash.locality_agg`, `snaptrash.enzyme_alerts` | `snaptrash.scans`, `snaptrash.msw_baseline` |

Stick to those schemas → integration is automatic.

## Quick Start

```bash
# 1. Clone + env
git clone <repo>
cd SmartWaste
cp .env.example .env   # fill in DATABRICKS_TOKEN, AWS keys, GROQ_API_KEY, etc.

# 2. Pick your app
cd apps/ingestion        # Person A
# or
cd apps/analytics        # Person B

uv sync                  # installs deps + editable common pkg

# 3. Bootstrap Databricks tables (once, after .env is filled)
cd ../..
uv run --project apps/analytics python scripts/bootstrap_databricks.py

# 4. Run
# Ingestion API:
uv run --project apps/ingestion uvicorn snaptrash_ingestion.main:app --reload --port 8000

# Analytics jobs (one-off):
uv run --project apps/analytics python -m snaptrash_analytics.ingest.load_msw_dryad
uv run --project apps/analytics python -m snaptrash_analytics.aggregations.locality_agg
uv run --project apps/analytics python -m snaptrash_analytics.forecasting.prophet_forecast
```

## Branches

- `main` — integration / demos
- `dev/ingestion` — Person A
- `dev/analytics` — Person B

Merge into `main` when integration milestone is hit.

## MCP Servers

`.claude/settings.json` configures:
- **databricks-mcp** — query / inspect Delta Lake from Claude
- **firecrawl-mcp** — run Firecrawl scrape jobs from Claude

Frontend skills available at user level: `ui-ux-pro-max`, `21st-dev-magic`, `shadcn-ui`, framer.

## Secrets Checklist

| Key | Source |
|---|---|
| `DATABRICKS_HOST` / `DATABRICKS_TOKEN` | Databricks UI → User Settings → Developer → Access tokens |
| `DATABRICKS_WAREHOUSE_ID` | Databricks UI → SQL Warehouses → click warehouse → Connection details |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | AWS IAM user with S3 read/write on `snaptrash-bins` |
| `GROQ_API_KEY` | https://console.groq.com/keys |
| `FIRECRAWL_API_KEY` | https://www.firecrawl.dev/app |
| `SENDGRID_API_KEY` | https://app.sendgrid.com/settings/api_keys |
