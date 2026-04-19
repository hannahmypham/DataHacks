# SnapTrash — Restaurant Waste Intelligence Platform

Real-time CV + LLM pipeline that scans commercial waste bins, classifies food and plastic waste, scores sustainability (1–4 scale), and triggers voice + email alerts when plastic thresholds are exceeded.

**DataHacks 2025 Submission**

---

## Architecture

```
iOS Camera
  │  presigned PUT
  ▼
S3 (snaptrash-raw-incoming)
  │  Lambda trigger
  ▼
AWS Lambda
  ├─ Rekognition  — dedup (similarity > 0.85 → skip re-analysis)
  └─ Grok Vision  — classify food + plastic items
       │  enriched ScanRow
       ▼
  Databricks Delta (snaptrash.scans)
       │  02_aggregations + 03_prophet_forecast notebooks
       ▼
  INSIGHTS + LOCALITY_AGG tables
  (sustainability score 1–4, Prophet forecast, ZIP ranking)
       │
       ▼
FastAPI :8000  (/insights, /locality, /weekly-series, /scan/latest)
       │  Vite proxy /api
       ▼
React Dashboard  (shadcn/ui + recharts, 30s live refresh)

Voice Alerts: Vapi.ai call if plastic > 150 kg/week (locality)
Email Alerts: SMTP if plastic > 150 kg/week (dedup: 1 email/ZIP/7 days)
```

---

## Quickstart

### Prerequisites
- Python 3.11+, Node 18+
- Databricks workspace with SQL warehouse
- AWS account (S3 + Lambda + Rekognition + DynamoDB)
- xAI API key (Grok Vision)

### 1. Environment

```bash
cp .env.example .env
# Fill in all values — see .env.example for descriptions
```

Required vars:
```
DATABRICKS_HOST=https://your-workspace.azuredatabricks.net
DATABRICKS_TOKEN=dapi...
DATABRICKS_WAREHOUSE_ID=...
DATABRICKS_USER=you@email.com
DATABRICKS_CATALOG=workspace
S3_BUCKET=snaptrash-bins
S3_RAW_BUCKET=snaptrash-raw-incoming
XAI_API_KEY=xai-...
```

### 2. Bootstrap Databricks tables

```bash
cd scripts
python bootstrap_databricks.py
python seed_fake_scans.py   # optional: 280 synthetic scans for demo
```

### 3. Start backend

```bash
cd apps/ingestion
pip install -e ../../packages/common -e .
uvicorn snaptrash_ingestion.main:app --reload --port 8000
```

API docs: `http://localhost:8000/docs`

### 4. Start frontend

```bash
cd apps/frontend
npm install
npm run dev   # http://localhost:5173
```

Vite proxies `/api/*` → `http://localhost:8000`.

### 5. Run analytics (Databricks)

Upload notebooks from `apps/analytics/notebooks/` to your Databricks workspace at `/Users/{DATABRICKS_USER}/snaptrash/`. Run manually or let `pipeline_trigger` auto-submit after each scan (90s cooldown).

### 6. Voice + email alerts (optional)

```bash
# Set in .env: VAPI_API_KEY, VAPI_ASSISTANT_ID, VAPI_PHONE_NUMBER_ID
#              DEFAULT_ALERT_PHONE, SMTP_USER, SMTP_PASS
#              ALERT_FROM_EMAIL, ALERT_TO_EMAILS

cd apps/voice-alerts
pip install -e ../../packages/common -e .
python -m snaptrash_voice_alerts.trigger
```

---

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Service health check |
| POST | `/scan` | Upload image (multipart) → full pipeline |
| GET | `/upload-url` | Presigned S3 PUT URL for iOS direct upload |
| GET | `/scan/latest/{restaurant_id}` | Most recent scan row |
| GET | `/insights/{restaurant_id}` | 7-day aggregates + score + Prophet forecast |
| GET | `/locality/{zip}` | ZIP-level plastic + sustainability stats |
| GET | `/weekly-series/{restaurant_id}` | Day-of-week actual food kg (past 7 days) |

---

## Sustainability Score (1–4 scale)

Five equally-weighted signals (20% each):

| Signal | Measures | Reference |
|--------|----------|-----------|
| S1 | Food kg vs ZIP average (1% rule) | EPA MSW 2022 |
| S2 | Banned + harmful plastic penalty | CA SB-54, IARC Group 2B |
| S3 | Recyclability rate (PET/HDPE/PP) | EPA MSW 2022 |
| S4 | Total plastic kg vs ZIP average | ZIP rolling 7d |
| S5 | Week-over-week reduction | EPA 20% voluntary goal |

`score = 1.0 + (raw_0_100 / 100) × 3.0`  →  clamped to [1.0, 4.0]

**Tiers:** Thriving Forest ≥3.7 · Full Tree ≥3.4 · Growing Plant ≥3.1 · Small Sprout ≥2.8 · Seed ≥2.5 · Bare Root <2.5

---

## Project Structure

```
apps/
  ingestion/        FastAPI service — scan ingestion + analytics routes
  analytics/        Databricks notebooks + Python aggregation scripts
  frontend/         Vite + React + shadcn/ui live dashboard
  voice-alerts/     Vapi.ai voice calls + SMTP email alerts
packages/
  common/           Shared schemas, env, table DDL, Databricks client, jobs API
infrastructure/
  lambda-detector/  AWS Lambda S3 trigger (Rekognition dedup + Grok pipeline)
scripts/
  bootstrap_databricks.py   Create all Delta tables
  seed_fake_scans.py        Generate 280 synthetic demo rows
  voice_alert_call.py       Manual alert trigger
data/
  epa_banned.json   Banned plastic polymers by state (SB-54, SB-270, NY S1185, WA SB 5022…)
```

---

## Alert Thresholds

| Alert | Threshold | Dedup |
|-------|-----------|-------|
| Locality plastic | >150 kg/week across ZIP | 1 email/ZIP/7 days (EMAIL_ALERTS table) |
| Restaurant plastic | >30 kg/week per restaurant | per-run only |
| Rekognition dedup | similarity >0.85 | per-image (DynamoDB) |

---

## Key Dependencies

**Backend:** FastAPI · Pydantic · httpx · databricks-sql-connector · boto3 · Prophet (Databricks)  
**Frontend:** React 18 · Vite · shadcn/ui · Recharts · TanStack Query · Tailwind CSS  
**Infrastructure:** AWS Lambda · S3 · Rekognition · DynamoDB · Databricks Delta Lake · Vapi.ai
