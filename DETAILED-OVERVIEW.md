# SnapTrash - Complete Project Overview & Getting Started

**For complete beginners**: This document explains *everything* about the SmartWaste/SnapTrash repository from scratch. No prior knowledge assumed. It covers what the app does, the full folder structure, how data moves through the system (data flow), key concepts, and step-by-step instructions to get the **entire application live and running** on your machine (development setup) or in production-like environments.

---

## What is SnapTrash?

SnapTrash is an AI-powered restaurant waste intelligence platform. It helps restaurants:

- **Snap a photo** of their waste bin using a mobile/web app.
- **AI analyzes the photo** (using Groq's vision model) to detect:
  - Food waste (type, decay stage, contamination, estimated weight, shelf life, dollar value, CO₂ impact).
  - Plastic waste (type, resin code, color, black plastic detection, polymer classification, recyclability, harmful/banned status per EPA rules).
- **Stores all data** in Databricks Delta Lake (a modern data lakehouse for analytics).
- **Runs automated analytics** (aggregations, forecasts using Prophet ML model, percentile rankings vs. local restaurants, threshold alerts).
- **Shows beautiful dashboards** with charts, maps (San Diego neighborhoods), gamification (e.g., "You're better than 77% of La Jolla restaurants!"), and live results.
- **Triggers real-world impact**: When plastic thresholds (e.g., PET volume) are exceeded in a locality, it sends emails to enzyme labs (via SendGrid) that can break down the plastics biologically. This creates a "demand signal" loop between restaurants and innovators.

**Key simplifications** (from the `snaptrash-plan.md`):
- No barcode scanning or manufacturer ID extraction (features fully removed).
- Focus on core CV analysis, enrichment, Databricks pipeline, and dashboard.
- Uses real datasets like US Municipal Solid Waste (Dryad) for benchmarks.

**Tech stack highlights**:
- **AI/ML**: Groq Vision (Llama model), Prophet forecasting (via Databricks MLflow).
- **Backend**: FastAPI (Python).
- **Data platform**: Databricks (Delta Lake tables, SQL Warehouse, Workflows).
- **Storage**: AWS S3 for images.
- **Frontend**: React + Vite + TypeScript + Tailwind CSS + Recharts (charts) + Mapbox.
- **Packaging**: `uv` (modern Python tool replacing pip/poetry), pnpm for frontend, shared Python package.
- **Scraping**: Firecrawl for EPA data, labs, etc.

The project follows a **team split** from the hackathon plan (ingestion vs. analytics vs. frontend).

See `snaptrash-plan.md` for the original 24-hour build plan and detailed architecture diagrams.

---

## Repository Structure

This is a **monorepo** (one repo with multiple apps/packages). Organized for collaboration between "Person A" (ingestion pipeline), "Person B" (analytics), and frontend work.

```
SmartWaste/ (root)
├── .env.example                  # Template for all secrets (copy to .env)
├── README.md                     # Short intro + quick start
├── DETAILED-OVERVIEW.md          # ← You are reading this comprehensive guide
├── snaptrash-plan.md             # Original detailed architecture/plan (updated)
├── scripts/                      # Utility scripts
│   ├── bootstrap_databricks.py   # Creates all Delta tables in Databricks
│   ├── seed_fake_scans.py        # Generates test data in DB
│   ├── run_dev.sh                # Runs API + frontend in parallel (dev)
│   └── ... (more bootstrap helpers)
├── packages/
│   └── common/                   # SHARED code used by ALL apps (critical!)
│       ├── pyproject.toml
│       └── src/snaptrash_common/
│           ├── __init__.py
│           ├── env.py            # Loads settings from .env (Databricks, AWS, API keys)
│           ├── schemas.py        # Pydantic models (FoodItem, PlasticItem, ScanRow, etc.)
│           ├── tables.py         # Delta Lake table DDL/SQL definitions
│           ├── databricks_client.py  # Reusable client for queries/inserts
│           └── ... 
├── apps/
│   ├── ingestion/                # "Person A" — Core pipeline (Stages 1-5)
│   │   ├── pyproject.toml        # deps + editable install of 'common'
│   │   ├── README.md
│   │   ├── tests/                # Unit tests for analysis
│   │   └── src/snaptrash_ingestion/
│   │       ├── main.py           # FastAPI app entrypoint
│   │       ├── routes/
│   │       │   ├── scan.py       # POST /scan endpoint (upload + full analysis)
│   │       │   └── health.py
│   │       ├── services/         # Business logic
│   │       │   ├── groq_vision.py    # Calls Groq Vision API with image + prompt
│   │       │   ├── food_analysis.py  # USDA shelf life, pricing, CO2 calc
│   │       │   ├── plastic_analysis.py # Resin→polymer, EPA harmful/banned checks
│   │       │   └── s3_client.py   # Uploads photos to AWS S3
│   │       ├── writers/
│   │       │   └── databricks_writer.py  # Inserts ScanRow to Delta Lake
│   │       └── ...
│   ├── analytics/                # "Person B" — Databricks jobs & insights (Stage 6+)
│   │   ├── pyproject.toml
│   │   ├── README.md
│   │   ├── notebooks/            # Jupyter-style .py files (load_msw, aggregations, prophet_forecast)
│   │   │   └── *.py              # Paired with Databricks notebooks
│   │   ├── tests/
│   │   ├── src/snaptrash_analytics/
│   │   │   ├── ingest/           # Load MSW dataset, Firecrawl jobs
│   │   │   ├── aggregations/     # SQL for rolling stats, locality_agg, threshold_check
│   │   │   ├── forecasting/      # Prophet model training & predictions
│   │   │   ├── readers/          # Queries for insights (used by frontend/API)
│   │   │   └── ...
│   │   └── data/                 # gitignored: scraped JSONs, Dryad CSVs
│   └── frontend/                 # React dashboard (Vite + TS)
│       ├── package.json          # pnpm deps (React, Tailwind, Recharts, Mapbox)
│       ├── vite.config.ts
│       ├── tailwind.config.ts
│       ├── src/
│       │   ├── App.tsx           # Main app with scan screen, results, weekly dashboard, map
│       │   ├── lib/api.ts        # Polls ingestion API + Databricks readers
│       │   ├── lib/cn.ts         # Utility for classnames
│       │   ├── main.tsx
│       │   └── ... (components for cards, charts, camera upload, etc.)
│       ├── index.html
│       └── ...
├── .git/                         # Git history (branches: main, dev/ingestion, dev/analytics)
├── claude/settings.json          # MCP servers (Databricks, Firecrawl) for AI assistance
└── gitignore / other config
```

**Key design principle**: Loose coupling via shared `packages/common` schemas and tables. Ingestion **only writes** to `snaptrash.scans`. Analytics **reads** it and writes computed tables. Frontend polls both.

---

## Data Flow (End-to-End)

Here's how everything connects (updated to remove barcode/manufacturer features):

1. **User Interaction (Frontend)**:
   - Open app → "Snap Bin" button opens camera.
   - Photo + metadata (restaurant_id, zip, neighborhood) sent to `POST /scan`.
   - Polls `GET /insights/{restaurant_id}` and `GET /locality/{zip}` every ~5s for live results.
   - Displays: Food/plastic breakdown cards, charts (Recharts), Mapbox neighborhood map, percentile badges, confetti gamification.

2. **Ingestion Service (FastAPI - apps/ingestion)**:
   - **Stage 1**: Receives image → uploads to AWS S3 (`s3://snaptrash-bins/{restaurant_id}/{timestamp}.jpg`). Returns presigned URL.
   - **Stage 2**: Calls Groq Vision API (with detailed JSON prompt for `food_items[]` + `plastic_items[]`). Returns structured data (no `barcode_visible` or manufacturer).
   - **Stage 3**: Food enrichment (`food_analysis.py`):
     - USDA FoodKeeper API for shelf life.
     - Pricing/CO2 lookup tables.
     - Flags for contamination/decay.
   - **Stage 4**: Plastic enrichment (`plastic_analysis.py`):
     - Resin code → polymer (PET/HDPE/etc.).
     - Cross-ref with pre-scraped `epa_banned_plastics.json` (via Firecrawl).
     - Flags: harmful (phthalates, styrene, BPA, black plastic), banned by state, recyclable status.
     - Generates alerts/recommendations.
   - **Stage 5**: Aggregates metrics (kg, counts, $ waste, etc.) → creates `ScanRow` (Pydantic model) → serializes food/plastic lists as JSON → inserts into Databricks Delta Lake table `snaptrash.scans` (partitioned by zip/date). Uses shared `databricks_client`.

3. **Analytics Pipeline (apps/analytics + Databricks)**:
   - **Reference Data**: 
     - Load US MSW Dryad dataset → `snaptrash.msw_baseline` (benchmarks/thresholds).
     - Firecrawl jobs scrape EPA bans, labs, compost facilities → JSON files loaded/used.
   - **Hourly Jobs** (SQL + Python, can be Databricks Workflows):
     - Aggregations: 7-day rolling stats per restaurant/locality (`locality_agg.py`, `restaurant_rolling.py`).
     - Forecasting: Prophet model per restaurant (time series on waste_kg/$) → predictions in `insights` table (tracked in MLflow).
     - Threshold detection: Compare vs. MSW baselines → populate `enzyme_alerts` if PET/plastic exceeds limits.
     - Percentile rankings, recommendations.
   - **Readers**: `insights_reader.py` provides clean queries for frontend/API.
   - **Output Tables** (defined in `tables.py`):
     - `snaptrash.scans` (raw + enriched)
     - `snaptrash.msw_baseline`
     - `snaptrash.insights` (weekly stats, forecast, percentile)
     - `snaptrash.locality_agg` (neighborhood summaries, enzyme_alert flag)
     - `snaptrash.enzyme_alerts` (for SendGrid notifications)

4. **Notifications & Impact**:
   - FastAPI or Databricks job polls `enzyme_alerts`.
   - SendGrid sends targeted emails to labs (e.g., "PET threshold exceeded in La Jolla — 2.8t").
   - Labs can respond → closes the loop.

5. **Frontend Polling/Dashboard**:
   - Live results cards (food left | plastic right with color badges: ✅/⚠️/❌).
   - Charts: trends, forecasts, breakdowns.
   - Map: Choropleth of neighborhoods by waste intensity.
   - All data pulled from Databricks via API layer.

**Data lives primarily in Databricks Delta Lake** (cloud data warehouse + lake). Everything else is transient (S3 images, API responses).

**Note on removed features**: No ZXing barcode decoding, no GS1 manufacturer lookup, no `manufacturer` or `barcode_visible`/`text_visible` in models/prompts/outputs. Plastic analysis is now purely visual + EPA-based.

---

## Key Schemas (from `packages/common/src/snaptrash_common/schemas.py`)

- `FoodItem`: type, decay_stage (0-5), kg, contaminated, compostable, enriched shelf_life/dollar/co2.
- `PlasticItem`: type, resin_code, color, is_black_plastic, estimated_count, enriched polymer/status/recyclable/harmful/alert.
- `ScanRow`, `InsightRow`, `LocalityAggRow`, `EnzymeAlertRow`: Match Delta table columns exactly (JSON blobs for nested items).
- `GroqVisionResult`: Top-level response from vision API.

See `tables.py` for full CREATE TABLE SQL (partitioned Delta tables).

---

## How to Get the Entire Application Live and Running

### Prerequisites
- **Accounts & Keys** (fill in `.env`):
  - Databricks workspace (free trial/community edition OK; get HOST, personal access TOKEN, SQL Warehouse ID).
  - AWS IAM user with S3 bucket write access (`snaptrash-bins` — create if needed).
  - Groq API key (console.groq.com).
  - Firecrawl API key (for scraping).
  - Optional: SendGrid, USDA API, Mapbox public token.
- **Tools**: 
  - Python 3.11+, `uv` (install via `curl -LsSf https://astral.sh/uv/install.sh | sh`).
  - Node.js/pnpm (for frontend).
  - Git.
- **Optional**: Databricks CLI, AWS CLI, tmux for running multiple services.

### Step-by-Step Setup

1. **Clone and Environment**:
   ```bash
   git clone <your-repo-url> SmartWaste
   cd SmartWaste
   cp .env.example .env
   # Edit .env with your real keys (see root README.md for sources)
   ```

2. **Install Dependencies** (uses `uv` for Python monorepo + editable common package):
   ```bash
   # From root or per-app
   cd apps/ingestion && uv sync
   cd ../analytics && uv sync
   # Frontend:
   cd ../frontend && pnpm install
   ```

3. **Bootstrap Databricks** (creates catalog/schema + all tables):
   ```bash
   uv run --project apps/analytics python scripts/bootstrap_databricks.py
   ```
   - Run once. Uses settings from `.env`. Check Databricks UI (SQL editor) afterward.

4. **Load Reference Data**:
   ```bash
   # MSW dataset + Firecrawl (EPA, labs, etc.)
   uv run --project apps/analytics python -m snaptrash_analytics.ingest.load_msw_dryad
   uv run --project apps/analytics python -m snaptrash_analytics.ingest.firecrawl_jobs
   ```
   - Populates `msw_baseline` and JSON files.

5. **Run the Full Stack (Development)**:
   ```bash
   # Easiest — runs ingestion API (:8000) + frontend (:5173) in parallel
   ./scripts/run_dev.sh
   ```
   - Or manually:
     - Ingestion API: `uv run --project apps/ingestion uvicorn snaptrash_ingestion.main:app --reload --port 8000`
     - Frontend: `cd apps/frontend && pnpm dev`
     - Analytics jobs (manual/cron): See `apps/analytics/README.md` (e.g., `uv run --project apps/analytics python -m snaptrash_analytics.aggregations.locality_agg`, Prophet forecast, etc.).
   - Visit `http://localhost:5173` for the dashboard. Test scan by uploading images.

6. **Seed Test Data** (for realistic dashboard):
   ```bash
   uv run --project apps/analytics python scripts/seed_fake_scans.py
   ```
   - Generates 4 weeks of fake restaurant scans.

7. **Test the Flow**:
   - Use the frontend camera/scan or curl the `/scan` endpoint with an image.
   - Check Databricks tables (use MCP/Databricks UI or `databricks_client`).
   - Trigger analytics jobs → see insights update.
   - Verify health: `curl http://localhost:8000/health`.

8. **Advanced / Production**:
   - **Databricks Workflows**: Schedule hourly aggregations/forecasts/thresholds (use notebooks or jobs).
   - **Cloud Intelligence Layer (S3 + Lambda + Rekognition)**: New S3 event-triggered Lambda on `snaptrash-raw-incoming` bucket performs change detection using Rekognition DetectLabels against DynamoDB `snaptrash-last-analyzed` reference. Similar images are deleted; different images are copied to `snaptrash-analyzed` and trigger the full Grok pipeline. See new flow in [snaptrash-plan.md](snaptrash-plan.md:67). MCP for Lambda added to `.claude/settings.json` (uses same AWS credentials as S3).
   - **Frontend Deploy**: Build with `pnpm build` → host on Vercel/Netlify (update CORS).
   - **API Deploy**: FastAPI to Railway, Fly.io, or AWS/EC2. Add env vars.
   - **Notifications**: Implement full SendGrid polling on `enzyme_alerts`.
   - **MCP Integration**: The `.claude/settings.json` now includes Databricks, Firecrawl, and Lambda tools for querying live data, buckets, and Rekognition results.
   - **Notebooks**: Sync `apps/analytics/notebooks/*.py` to Databricks Repos for interactive SQL/MLflow.
   - **Branches**: Work on `dev/ingestion` or `dev/analytics`, merge to `main`.
   - **Tests**: `uv run pytest` in app dirs.
   - **Scaling**: Use Databricks Serverless SQL Warehouse for queries; add auth (restaurant login).

**Common Issues**:
- Missing keys → check `settings.py` validation.
- Databricks permissions: Ensure token has SQL Warehouse + catalog access.
- Image uploads: Must be valid JPEG/PNG.
- Frontend CORS: Update `CORS_ORIGINS` in `.env`.
- First run: Bootstrap + seed data is mandatory for dashboard to show content.

---

## Next Steps & Resources

- **Explore code**: Start with `packages/common/schemas.py`, then `apps/ingestion/routes/scan.py` (the heart of the pipeline), then analytics notebooks.
- **AI Assistance**: Use Cursor's MCP servers (Databricks query, Firecrawl) or the `ui-ux-pro-max` skill for frontend.
- **Extend**: Add user auth, more CV models, real-time WebSockets, mobile app (React Native), or full enzyme lab dashboard.
- **Demo**: Use real food/plastic items + camera for live scans during presentations.
- Full original plan: `snaptrash-plan.md` (includes prize categories, team split, Firecrawl jobs).

This setup gets you a **fully functional end-to-end AI waste analytics platform** in minutes once keys are configured. The architecture is production-ready with Databricks as the single source of truth.

Questions? Check logs (`LOG_LEVEL=DEBUG`), Databricks query history, or the individual READMEs. Happy building!

*Last updated: Based on current repo state (post-barcode/manufacturer removal).*
