# SnapTrash — Complete Build Plan

## Tool → Role Mapping

| Tool | Role in SnapTrash |
|---|---|
| **Groq Vision API** | CV: food/plastic segmentation, decay detection, resin code reading |
| **Firecrawl** | Scrape EPA banned plastics, BioCycle compost dirs, enzyme labs |
| **Databricks** (`ai-dev-kit`) | Delta Lake ingestion, SQL aggregation, Prophet forecast, threshold detection, primary data store |
| **Lovable** | Build frontend dashboard UI fast |
| **sales-dashboard** | React/Vite base — repurpose into SnapTrash UI |
| **FastAPI** | Backend orchestrator — calls Groq, writes Databricks, triggers SendGrid |
| **AWS S3** | Store uploaded bin photos |
| **SendGrid** | Auto-email enzyme labs when threshold breached |
| **US Municipal Solid Waste** | Thresholds + state benchmarks loaded into Databricks |

---

## Dataset Usage (Compliance)

**Primary:** US Municipal Solid Waste (Dryad) — non-Scripps ✅ satisfies requirement

```
What you use from it:
- State-level commercial waste volumes → set locality thresholds
- Historical trend 1996–2019 → calibrate Prophet forecast baseline
- State averages → restaurant percentile ranking ("top 23% in CA")
Load into: Databricks Delta Lake as reference table: snaptrash.msw_baseline
```

---

## Full Architecture

```
📷 Photo
    ↓
AWS S3 (image store)
    ↓
FastAPI (orchestrator)
    ├── Groq Vision API → analysis JSON
    ├── USDA API → shelf life
    ├── EPA lookup → plastic flags
    └── Databricks SQL Warehouse → INSERT scan row
              ↓
    Databricks Delta Lake (ALL data here)
              ↓
    Databricks Workflows (hourly)
    ├── SQL aggregations → locality_agg table
    ├── Prophet forecast → insights table
    └── Threshold check → enzyme_alerts table
              ↓
    FastAPI reads → Frontend polls (5s)
              ↓
    Lovable React dashboard

    IF enzyme_alerts has new row:
    FastAPI → SendGrid → lab email
```

---

## Stage-by-Stage Pipeline

---

### STAGE 1 — Image Capture

```
INPUT:  Restaurant opens app → taps "Snap Bin" → camera opens
OUTPUT: Image uploaded to AWS S3

Tool:   Lovable frontend (React camera API)
        → AWS S3 presigned URL upload
        → AWS Lambda triggered on S3 PUT

S3 path: s3://snaptrash-bins/{restaurant_id}/{unix_timestamp}.jpg
```

---

### STAGE 2 — Groq Vision CV Analysis

```
INPUT:  S3 image URL
OUTPUT: Structured JSON — food items + plastic items

Tool:   Groq Vision API (llama-4-scout-17b or llama-3.2-11b-vision)

FastAPI calls Groq:
POST https://api.groq.com/openai/v1/chat/completions
{
  model: "llama-4-scout-17b-16e-instruct",
  messages: [{
    role: "user",
    content: [
      { type: "image_url", image_url: { url: s3_presigned_url } },
      { type: "text", text: PROMPT }
    ]
  }]
}

PROMPT:
"Analyze this restaurant waste bin image. Return JSON:
{
  food_items: [{
    type: string,           // 'leafy greens', 'cooked rice', 'raw chicken'...
    decay_stage: 0-5,       // 0=fresh, 5=spoiled
    color_description: str,
    mold_visible: bool,
    estimated_kg: float,
    contaminated: bool,     // cross-contamination risk
    compostable: bool
  }],
  plastic_items: [{
    type: string,           // 'water bottle', 'foam container', 'cling wrap'
    resin_code: int,        // 1-7 if visible, null if not
    color: string,
    is_black_plastic: bool,
    estimated_count: int
  }]
}"

OUTPUT JSON example:
{
  food_items: [
    { type: "leafy greens", decay_stage: 2, estimated_kg: 1.2,
      contaminated: false, compostable: true, mold_visible: false },
    { type: "raw chicken", decay_stage: 4, estimated_kg: 0.8,
      contaminated: true, compostable: false, mold_visible: true }
  ],
  plastic_items: [
    { type: "foam container", resin_code: 6, is_black_plastic: false },
    { type: "water bottle", resin_code: 1, is_black_plastic: false }
  ]
}
```

---

### STAGE 3 — Food Waste Analysis

```
INPUT:  food_items[] from Stage 2
OUTPUT: Per-item shelf life, dollar value, compost status

Tools:  USDA FoodKeeper API + USDA retail price table

Per food item:
A. Shelf Life
   GET https://foodkeeper.usda.gov/api/products?name={type}
   → shelf_life_days (refrigerated)
   remaining_days = shelf_life_days - decay_days_estimate(decay_stage)

B. Contamination Check
   contaminated=true OR decay_stage>=4 → cannot compost, flag red

C. Dollar Wastage
   food_type → USDA avg retail price per kg (pre-loaded lookup table)
   dollar_value = estimated_kg × price_per_kg

D. CO2 Equivalent
   food_type → FAO emission factor (kg CO2 per kg food wasted)
   co2_kg = estimated_kg × emission_factor

OUTPUT per item:
{
  type: "leafy greens",
  shelf_life_remaining: "3 days",
  compostable: true,
  contaminated: false,
  dollar_value: 4.80,
  co2_kg: 2.1
}
```

---

### STAGE 4 — Plastic Waste Analysis

```
INPUT:  plastic_items[] from Stage 2
OUTPUT: Per-item polymer classification, harmful flag, recyclability

Tools:  Pre-scraped JSON files (Firecrawl)

A. Polymer Classification
   resin_code → polymer type mapping:
   {1:PET, 2:HDPE, 3:PVC, 4:LDPE, 5:PP, 6:PS, 7:Other}
   If no resin_code → Groq already inferred from visual

C. Harmful/Banned Check
   Cross-reference: epa_banned_plastics.json (Firecrawl scraped)
   {polymer_type, state} → status: recyclable | harmful | banned

   Harmful flags:
   PVC #3 → phthalates ⚠️
   PS #6 → styrene ⚠️ + banned in CA/NY/ME
   PC #7 → BPA ⚠️
   black_plastic=true → flame retardants ⚠️ + unrecyclable

D. Recyclability
   PET + HDPE + PP → recyclable ✅
   PVC + PS + black → NOT recyclable ❌
   PFAS-coated → NOT recyclable + harmful ⚠️

OUTPUT per item:
{
  polymer_type: "PS",
  resin_code: 6,
  status: "banned_CA",
  recyclable: false,
  harmful: true,
  alert: "PS foam banned in CA since 2023. Switch to PET clamshell."
}
```

---

### STAGE 5 — Write Scan to Databricks

```
INPUT:  Stage 3 + 4 analysis output
OUTPUT: Row appended to Delta Lake

Tool:   databricks-sdk (from ai-dev-kit/databricks-tools-core)

from databricks.sdk import WorkspaceClient

w = WorkspaceClient()  # uses env vars DATABRICKS_HOST + DATABRICKS_TOKEN

w.statement_execution.execute_statement(
  warehouse_id=WAREHOUSE_ID,
  statement="""
    INSERT INTO snaptrash.scans VALUES (
      :scan_id, :restaurant_id, :zip, :neighborhood, :timestamp,
      :food_kg, :compostable_kg, :contaminated_kg,
      :dollar_wastage, :co2_kg,
      :plastic_count, :harmful_plastic_count,
      :pet_kg, :ps_count,
      :food_items_json, :plastic_items_json
    )
  """,
  parameters={...}
)
```

---

### STAGE 6 — Databricks Analytics Pipeline (Core)

```
Tool:   Databricks (ai-dev-kit/databricks-tools-core)
        Delta Lake + Databricks SQL + MLflow

A. INGEST (Auto Loader)
   Scan logs → Delta Lake
   Table: snaptrash.scans (partitioned by date, zip)

   ALSO load at start:
   US Municipal Solid Waste CSV (Dryad dataset)
   → Delta table: snaptrash.msw_baseline

B. AGGREGATION (Databricks SQL, runs hourly)

   -- Restaurant 7-day rolling stats
   SELECT restaurant_id,
     SUM(dollar_wastage) as weekly_dollar_waste,
     SUM(food_kg) as weekly_food_kg,
     SUM(ps_count) as weekly_ps_count,
     SUM(pet_kg) as weekly_pet_kg,
     AVG(compostable_kg/food_kg) as compost_yield_rate
   FROM snaptrash.scans
   WHERE timestamp >= NOW() - INTERVAL 7 DAYS
   GROUP BY restaurant_id

   -- Locality aggregation
   SELECT zip, neighborhood,
     SUM(pet_kg) as total_pet_kg,
     SUM(ps_count) as total_ps_count,
     SUM(harmful_plastic_count) as harmful_count,
     COUNT(DISTINCT restaurant_id) as active_restaurants
   FROM snaptrash.scans
   WHERE timestamp >= NOW() - INTERVAL 7 DAYS
   GROUP BY zip, neighborhood

   -- Threshold from MSW baseline
   SELECT state, avg_commercial_waste_kg_per_restaurant
   FROM snaptrash.msw_baseline
   WHERE year = 2019

C. FORECASTING (MLflow on Databricks)
   Prophet model per restaurant:
   Input: daily food_kg + dollar_wastage time series
   Output: 7-day forecast
   "Next week projected: $340 waste (+15% above your avg)"
   Tracked in MLflow: model version, RMSE, params

D. PERCENTILE RANKING
   PERCENT_RANK() OVER (
     PARTITION BY neighborhood, date_trunc('week', timestamp)
     ORDER BY food_kg ASC
   ) as percentile
   → "You're better than 77% of La Jolla restaurants this week"

E. THRESHOLD DETECTION
   IF total_pet_kg_7day > (msw_state_avg × restaurant_count × 0.8)
   → SET enzyme_alert = true, alert_zip = zip

F. SUSTAINABILITY SCORE + BADGE (runs after B + D, per restaurant per week)

   Input fields (all from rolling 7-day window):
   - contaminated_kg, food_kg          → contamination_rate
   - harmful_plastic_count, plastic_count → harmful_packaging_rate
   - food_kg this week vs last week    → waste_trend_direction
   - food_kg delta week-over-week      → improvement_delta
   - locality_percentile (from step D) → peer_score

   Component scores (each 0–100):

   contamination_score  = (1 - contaminated_kg / NULLIF(food_kg, 0)) * 100
   packaging_score      = (1 - harmful_plastic_count / NULLIF(plastic_count, 0)) * 100
   trend_score          = CASE
                            WHEN food_kg_this_week < food_kg_last_week * 0.95 THEN 100
                            WHEN food_kg_this_week < food_kg_last_week * 1.05 THEN 50
                            ELSE 0
                          END
   improvement_score    = LEAST(100, GREATEST(0,
                            (food_kg_last_week - food_kg_this_week)
                            / NULLIF(food_kg_last_week, 0) * 300
                          ))
   peer_score           = locality_percentile * 100

   Weighted total:
   sustainability_score = ROUND(
     contamination_score  * 0.30 +
     packaging_score      * 0.25 +
     trend_score          * 0.20 +
     improvement_score    * 0.15 +
     peer_score           * 0.10
   , 1)

   Badge assignment:
   score 91–100 → "Green Leader"
   score 76–90  → "Gold"
   score 61–75  → "Silver"
   score 41–60  → "Bronze"
   score 0–40   → null (no badge)

   Feedback message (FastAPI assembles from fields):
   "Sustainability Score: {score}/100 — {badge}. 
    You're doing better than {percentile}% of restaurants in {neighborhood} this week."

G. WRITE BACK computed results to Delta tables
   insights/{restaurant_id} → weekly_dollar_waste, forecast, percentile, recommendation,
                               sustainability_score, badge_tier, score_feedback_message
   locality_agg/{zip} → aggregated plastic + food metrics
   enzyme_alerts → zip, threshold, volume, timestamp
```

---

### STAGE 7 — Frontend Dashboard (Lovable)

```
Tool:   Lovable → generates React components
        Base: repurpose sales-dashboard (Vite + React already set up)

Frontend polls FastAPI every 5 seconds:

GET /insights/{restaurant_id}
  → SELECT * FROM snaptrash.insights
     WHERE restaurant_id = :id
     ORDER BY computed_at DESC LIMIT 1

GET /locality/{zip}
  → SELECT * FROM snaptrash.locality_agg WHERE zip = :zip

GET /scan-results/{scan_id}
  → SELECT * FROM snaptrash.scans WHERE scan_id = :id

Lovable prompts to generate:
1. "Camera scan screen with upload button and live preview"
2. "Two-column results card: food analysis left, plastic analysis right,
    with color-coded severity badges"
3. "Weekly waste trend line chart with forecast dotted line using Recharts"
4. "Mapbox choropleth map of San Diego neighborhoods colored by plastic usage"
5. "Gamification popup: confetti animation + sustainability score (0-100) + badge tier (Bronze/Silver/Gold/Green Leader) + percentile message"

Screens:

① SCAN SCREEN
  [📷 Snap Bin] button → camera → upload → loading spinner

② RESULTS SCREEN (appears in ~3 seconds)
  ┌─────────────────┬──────────────────┐
  │ 🥦 FOOD WASTE   │ 🧴 PLASTIC       │
  │ Leafy greens    │ PS Foam ⚠️ BANNED│
  │ 3 days left     │                  │
  │ Compost ✅      │ Recyclable       │
  │ $4.80 wasted    │                  │
  │ Raw chicken     │ PET Bottle ✅    │
  │ CONTAMINATED ❌  │                  │
  └─────────────────┴──────────────────┘

  POPUP: "🎉 Score: 84/100 — Silver Badge. Better than 77% of La Jolla today!"

③ WEEKLY DASHBOARD
  Line chart: waste_kg per day + forecast
  Donut: food category breakdown
  Stat cards: $187 wasted | 8.3kg CO2 | 2 harmful plastics

④ MAP VIEW (Mapbox)
  San Diego split by neighborhood
  Color: green→yellow→red by plastic intensity
  User's restaurant pinned
  "North Park: 1.8t PET 🟡 approaching threshold"
```

---

### STAGE 8 — Enzyme Lab Notification

```
INPUT:  Databricks enzyme_alerts has new row
OUTPUT: Email to matched labs

Tool:   SendGrid API + pre-scraped lab directory (Firecrawl)

Firecrawl scraped targets:
- carbios.com (PETase industrial)
- ReFED enzyme solutions listings
- University lab public contact pages (UCSD, UCLA, Scripps)
→ labs.json: [{name, enzyme_types:["PET"], contact_email, region}]

Matching logic (FastAPI):
1. Poll snaptrash.enzyme_alerts every 5 min
2. Filter labs.json by enzyme_type=PET + region covers alert_zip
3. SendGrid email:

Subject: "DEMAND SIGNAL — La Jolla 92037 — PET Threshold Exceeded"
Body:
  Locality: La Jolla, CA 92037
  PET volume (7-day): 2.8 tons
  Threshold: 2.5 tons
  Forecast peak: 3.4 tons in 9 days
  Carbon credits available: 14.2 tCO2e
  [View Dashboard] [Confirm Production Interest]

Restaurant sees: "⚗️ Enzyme deployment triggered for your locality"
```

---

## Firecrawl Scraping Jobs (Run at Hackathon Start — Hour 1)

```python
from firecrawl import FirecrawlApp

app = FirecrawlApp(api_key="...")

# 1. EPA banned plastics by state
epa = app.scrape_url("https://www.epa.gov/trash-free-waters/plastic-bans",
                     formats=["json"])

# 2. BioCycle compost facilities
biocycle = app.crawl_url("https://www.biocycle.net/compost-facility-directory/",
                          limit=200)

# 3. Enzyme labs
labs = app.crawl_url("https://www.refd.org/solutions?category=enzyme",
                     limit=50)

# Save all to JSON files → load into FastAPI at startup
```

---

## Full Table Schema

```sql
-- Primary scan log
CREATE TABLE snaptrash.scans (
  scan_id STRING,
  restaurant_id STRING,
  zip STRING,
  neighborhood STRING,
  timestamp TIMESTAMP,
  food_kg DOUBLE,
  compostable_kg DOUBLE,
  contaminated_kg DOUBLE,
  dollar_wastage DOUBLE,
  co2_kg DOUBLE,
  plastic_count INT,
  harmful_plastic_count INT,
  pet_kg DOUBLE,
  ps_count INT,
  food_items_json STRING,
  plastic_items_json STRING
) USING DELTA
PARTITIONED BY (zip, date(timestamp));

-- MSW baseline (Dryad dataset)
CREATE TABLE snaptrash.msw_baseline (
  year INT,
  state STRING,
  waste_type STRING,
  total_tons DOUBLE,
  avg_commercial_waste_kg_per_restaurant DOUBLE
) USING DELTA;

-- Computed insights (pipeline writes, frontend reads)
CREATE TABLE snaptrash.insights (
  restaurant_id STRING,
  computed_at TIMESTAMP,
  weekly_dollar_waste DOUBLE,
  forecast_next_week DOUBLE,
  locality_percentile DOUBLE,
  top_waste_category STRING,
  recommendation STRING,
  co2_avoided DOUBLE,
  sustainability_score DOUBLE,       -- 0.0–100.0
  badge_tier STRING,                 -- 'Green Leader' | 'Gold' | 'Silver' | 'Bronze' | null
  score_feedback_message STRING      -- pre-assembled display string for frontend popup
) USING DELTA;

-- Locality aggregates
CREATE TABLE snaptrash.locality_agg (
  zip STRING,
  neighborhood STRING,
  computed_at TIMESTAMP,
  total_pet_kg DOUBLE,
  total_ps_count INT,
  harmful_count INT,
  active_restaurants INT,
  enzyme_alert BOOLEAN
) USING DELTA;

-- Enzyme alert log
CREATE TABLE snaptrash.enzyme_alerts (
  alert_id STRING,
  zip STRING,
  neighborhood STRING,
  triggered_at TIMESTAMP,
  pet_volume_7day DOUBLE,
  threshold DOUBLE,
  forecast_peak DOUBLE,
  notified BOOLEAN
) USING DELTA;
```

---

## Build Order — Hour by Hour

```
HOUR 1:    Firecrawl scraping → epa_banned.json, compost_facilities.json, labs.json
HOUR 1:    Load US Municipal Solid Waste CSV into Databricks Delta Lake (snaptrash.msw_baseline)
HOUR 2:    FastAPI skeleton + AWS S3 config
HOUR 2:    Groq API key test → confirm Vision model working
HOUR 3-5:  Stage 2-4: Groq Vision prompt + food analysis + plastic analysis
HOUR 5-6:  Stage 5: Databricks write (scans table)
HOUR 6-8:  Stage 6: Databricks SQL queries + Prophet forecast + threshold logic
HOUR 8-9:  Stage 8: SendGrid lab notification trigger
HOUR 9-13: Stage 7: Lovable frontend (scan + results + dashboard + map)
HOUR 14-15: Wire frontend → 5s polling FastAPI → Databricks
HOUR 16-17: Integration testing end-to-end
HOUR 18-20: Pre-load 4 weeks fake restaurant data into snaptrash.scans
HOUR 21-22: Mapbox map polish + gamification popup
HOUR 23-24: Demo rehearsal — bring real plastic + food to scan live
```

---

## Team Split (4 people)

| Person | Owns | Hours |
|---|---|---|
| **A** | Groq Vision prompt engineering + food/plastic analysis (Stage 2-4) | 1-8 |
| **B** | Databricks pipeline + MSW dataset + Prophet + thresholds (Stage 6) | 1-9 |
| **C** | FastAPI backend + AWS S3 + SendGrid + Databricks writes (Stage 1,5,8) | 1-9 |
| **D** | Lovable frontend + Mapbox + charts + demo polish (Stage 7) | 2-22 |

---

## Prize Stack

| Prize | Qualifier |
|---|---|
| **ML & Bio-AI track** $5000 | Groq Vision CV + decay ML + polymer classification |
| **Cloud Development track** $2000 | AWS S3/Lambda + Databricks cloud pipeline |
| **Best Use of Databricks** | Delta Lake + MLflow + SQL + Prophet — primary DB + analytics |
| **Best Use of AWS** | S3 + Lambda + EC2 inference |
| **Most Innovative Idea** | Enzyme lab signal loop |
| **Build with AI / Google** | Groq Vision as AI backbone |

**Potential total: ~$9000+**
