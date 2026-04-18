---
name: snaptrash
description: Comprehensive knowledge of the SnapTrash restaurant waste vision + analytics platform in the SmartWaste monorepo. Use for any work on ingestion pipelines, Databricks analytics, React dashboard, schema changes, data flow, or when user mentions SnapTrash, scans, plan.md, DETAILED-OVERVIEW.md, food/plastic analysis, Prophet forecasting, enzyme alerts, or Databricks Delta Lake. Enforces monorepo conventions (uv, shared common package), schema consistency between ingestion/analytics/frontend, the updated architecture (no barcode_visible or manufacturer ID extraction), and best practices from the plan.
---

# SnapTrash Project Skill

This skill provides persistent, project-specific guidance for the Grok agent when working in the SmartWaste/SnapTrash repository.

## Project Overview (Always Reference)

- **Purpose**: AI-powered platform that analyzes restaurant bin photos for food decay and plastic waste. Uses Groq Vision → enrichment → Databricks Delta Lake → analytics (SQL aggregations, Prophet forecasts, thresholds) → React dashboard + enzyme lab alerts via SendGrid.
- **Key Simplification**: Barcode scanning and manufacturer ID extraction features have been **completely removed**. Plastic analysis is now purely visual + EPA-based (resin code → polymer, harmful/banned flags).
- **Core Documents**:
  - `snaptrash-plan.md`: Original architecture, stages, table schemas, build order.
  - `DETAILED-OVERVIEW.md`: Full repo explanation, data flow, setup instructions, schemas.
- **Data Flow** (critical to preserve):
  1. Frontend (React/Vite/TS/Tailwind) → POST /scan (image + metadata).
  2. Ingestion (FastAPI): S3 upload → Groq Vision (food_items + plastic_items) → food_analysis.py + plastic_analysis.py enrichment → aggregate metrics → insert `ScanRow` (with JSON blobs) to `snaptrash.scans`.
  3. Analytics jobs: Load MSW Dryad + Firecrawl data → hourly aggregations, Prophet MLflow forecasts, threshold detection → write to `insights`, `locality_agg`, `enzyme_alerts`.
  4. Frontend polls API for insights/locality results (charts, map, gamification).
- **Monorepo Structure** (never break):
  - `packages/common/`: Shared Pydantic schemas (`FoodItem`, `PlasticItem`, `ScanRow`, `InsightRow`, etc.), `tables.py` (Delta DDL), `databricks_client.py`, `env.py`.
  - `apps/ingestion/`: FastAPI API, Groq/food/plastic services, Databricks writer. **Only writes** to `scans`.
  - `apps/analytics/`: Jobs, notebooks, readers for insights. **Reads scans**, writes computed tables.
  - `apps/frontend/`: React dashboard with camera, results cards, Recharts, Mapbox.
  - Scripts for bootstrap, seeding, dev server (`run_dev.sh`).
  - Use `uv sync` (per app, installs editable common).

## Coding & Architecture Rules

### Schema & Table Consistency (Critical)
- **Always** import and use models from `snaptrash_common.schemas` (`FoodItem`, `PlasticItem` without manufacturer/barcode fields, `ScanRow`, etc.).
- Match Pydantic models **exactly** to columns in `tables.py` and the Delta tables created by `bootstrap_databricks.py`.
- JSON fields (`food_items_json`, `plastic_items_json`) must serialize the enriched models.
- Never rename columns or break the ingestion ↔ analytics contract.

### Python / Ingestion Standards
- Use the shared `settings` from `snaptrash_common.env`.
- Keep services modular (`groq_vision.py`, `food_analysis.py`, `plastic_analysis.py`, `s3_client.py`).
- Lookup tables in `food_analysis.py` (SHELF_LIFE, PRICE_PER_KG, CO2_PER_KG) are placeholders — extend them or wire real USDA/FoodKeeper/FAO APIs when enhancing.
- Contamination logic: `decay_stage >= 4 or mold_visible → contaminated=True, compostable=False`.
- Error handling, type hints, and tests (`test_food_analysis.py`, `test_plastic_analysis.py`) must be maintained.

### Databricks & Analytics Standards
- All table operations via `databricks_client.py` or the SDK.
- Use Delta Lake best practices (partitioning by zip/date).
- Prophet forecasts in `forecasting/prophet_forecast.py`, aggregations in dedicated modules, readers for frontend.
- Firecrawl jobs for EPA/labs data (see `ingest/firecrawl_jobs.py`).
- Notebooks in `apps/analytics/notebooks/` should stay in sync with Databricks.

### Frontend & UI/UX Standards
- React + TypeScript + Tailwind + shadcn/ui patterns (leverage ui-ux-pro-max skill).
- Camera upload → results screen (two-column food/plastic cards with severity badges), weekly dashboard (Recharts trends/forecast), Mapbox choropleth.
- Poll API every ~5s for live data.
- Follow accessibility, responsive design, modern UX (see DETAILED-OVERVIEW.md for mockups).

### General Conventions
- **uv** for Python dependency management (`pyproject.toml` per app).
- Monorepo branches: `main`, `dev/ingestion`, `dev/analytics`.
- Keep the integration contract clean (only through common schemas/tables).
- When editing plan/overview docs, maintain accuracy about removed features.
- Use MCP servers (Databricks, Firecrawl) when querying live data or scraping.
- Follow `DETAILED-OVERVIEW.md` setup instructions exactly for running the stack (`bootstrap_databricks.py`, seed data, `run_dev.sh`).

## Trigger Conditions
- Automatically apply on any file edit in `apps/`, `packages/common/`, `scripts/`, or when `.md` files like plan/overview are open.
- Use when user asks about architecture, data flow, adding features, debugging pipelines, or running the app.
- **Always combine with**:
  - `databricks-snaptrash` (for analytics, tables, Prophet, MCP).
  - `firecrawl-snaptrash` (for all scraping, EPA/labs research).
  - `ui-ux-snaptrash` (for dashboard, Framer Motion animations, 21st.dev/shadcn components, accessibility).

## Examples

**Good edit to food_analysis.py**:
- Extend lookup dicts with new food types while preserving defaults and `_key()` fuzzy matching.
- Keep contamination logic unchanged unless explicitly requested.

**When adding a new aggregation**:
1. Add to `apps/analytics/src/snaptrash_analytics/aggregations/`.
2. Update relevant reader if exposing to frontend.
3. Ensure it writes to the correct computed table per schemas.
4. Update `DETAILED-OVERVIEW.md` if the data flow changes.

**Frontend change**:
- Use functional components, custom hooks (`lib/`), Tailwind classes.
- Maintain polling and two-column results layout from the plan.

Read `DETAILED-OVERVIEW.md` and `snaptrash-plan.md` for full context on first use of this skill.

## Integrated Global Marketplace Skills
- **databricks**: Full CLI, aitools, profiles, Unity Catalog, jobs, MLflow (project wrapper adds SnapTrash tables and jobs).
- **firecrawl**: All web/scraping/research (project wrapper adds specific EPA/BioCycle/labs jobs from the plan; **always use** for internet tasks).
- **ui-ux-pro-max + website-builder-setup**: 67 styles/palettes, Framer Motion animations, 21st.dev/shadcn components tailored to the exact dashboard screens (results cards, charts with forecast, Mapbox, gamification).

This skill ensures all Grok interactions stay consistent with the project's architecture, removed features, and monorepo design.
