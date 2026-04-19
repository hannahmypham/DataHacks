# SnapWaste — Data Flow & Card Wiring

## Full Pipeline

```
Photo → FastAPI /scan → S3 upload → Grok Vision → Databricks writer
                                                        ↓
                                              scans / synthetic_scans
                                                        ↓
                                               scans_unified (VIEW)
                                                        ↓
                          ┌─────────────────────────────┼──────────────────────────┐
                    restaurant_rolling.py        locality_agg.py            prophet_forecast.py
                          ↓                            ↓                          ↓
                      insights table             locality_agg table         insights (UPDATE forecasts)
                          ↓ (UPDATE)
                    sustainability_score.py
```

FastAPI reads `insights` + `locality_agg` via `insights_reader.py`
→ `GET /api/insights/:restaurant_id`
→ `GET /api/locality/:zip`

---

## Card → Field → Table → Job

### Screen 2 — Overview

| Card | Frontend field | Databricks column | Table | Written by |
|------|---------------|-------------------|-------|------------|
| Sustainability Score | `sustainability_score` | `sustainability_score` | `snaptrash.insights` | `sustainability_score.py` — 5 signals, equal 20% each |
| Badge Tier | `badge_tier` | `badge_tier` | `snaptrash.insights` | `sustainability_score.py` |
| Weekly $ Waste | `weekly_dollar_waste` | `weekly_dollar_waste` | `snaptrash.insights` | `restaurant_rolling.py` — SUM(dollar_wastage) from scans; USDA price × kg fallback |
| Forecast $ | `forecast_dollar_waste` | `forecast_dollar_waste` | `snaptrash.insights` | `prophet_forecast.py` — Prophet model, SD disposal trend as external regressor |
| ZIP Percentile | `locality_percentile` | `locality_percentile` | `snaptrash.insights` | `sustainability_score.py` — PERCENT_RANK within ZIP |
| Better Than | `better_than_count` / `zip_restaurant_count` | same columns | `snaptrash.insights` | `sustainability_score.py` |
| Peak Waste Day | `peak_waste_day` / `peak_waste_day_kg` | same columns | `snaptrash.insights` | `restaurant_rolling.py` — 28-day DOW query on `scans_unified` |
| Nearest Compost | `nearest_facility_name` / `nearest_facility_km` | same columns | `snaptrash.insights` | `sustainability_score.py` — haversine against `analytics.gold_composting_routes_ca` |
| Forecast Chart | `WEEKLY_SERIES` (currently hardcoded) | *not yet wired* | `scans_unified` daily aggregates | needs new `/api/weekly_series/:restaurant_id` endpoint |
| Recommendation | `recommendation` | `recommendation` | `snaptrash.insights` | `restaurant_rolling.py` — rule-based string |

### Screen 3 — Plastic

| Card | Frontend field | Databricks column | Table | Written by |
|------|---------------|-------------------|-------|------------|
| Plastic Volume | `weekly_plastic_count` | `weekly_plastic_count` | `snaptrash.insights` | `restaurant_rolling.py` — SUM(plastic_count) |
| Forecast Plastic | `forecast_plastic_count` | `forecast_plastic_count` | `snaptrash.insights` | `prophet_forecast.py` |
| Harmful / Banned | `harmful_plastic_count` + `ban_flag_count` | same columns | `snaptrash.insights` | `restaurant_rolling.py` (harmful); `sustainability_score.py` parses ban flags from `plastic_items_json` |
| CO2 Avoided | `co2_avoided` | `co2_avoided` | `snaptrash.insights` | `restaurant_rolling.py` — compostable_kg × 2.5 |
| Enzyme Alert | `enzyme_alert` | `enzyme_alert` | `snaptrash.locality_agg` | `locality_agg.py` — fires when pet_7d > active_restaurants × 50 × 0.8 |
| Active Restaurants | `locality.active_restaurants` | `active_restaurants` | `snaptrash.locality_agg` | `locality_agg.py` — COUNT(DISTINCT restaurant_id) |

### Screen 4 — Food

| Card | Frontend field | Databricks column | Table | Written by |
|------|---------------|-------------------|-------|------------|
| Food Waste kg / lbs | `weekly_food_kg` | `weekly_food_kg` | `snaptrash.insights` | `restaurant_rolling.py` — SUM(food_kg) |
| Forecast Food | `forecast_food_kg` | `forecast_food_kg` | `snaptrash.insights` | `prophet_forecast.py` |
| Shelf Life | `shelf_life_min_days` | `shelf_life_min_days` | `snaptrash.insights` | `restaurant_rolling.py` — USDA FoodKeeper from `analytics.gold_food_shelf_life`, cross-ref `prepped_at` from CV |
| At Risk kg | `at_risk_kg_24h` | `at_risk_kg_24h` | `snaptrash.insights` | `restaurant_rolling.py` — food items with ≤1 day remaining |
| Score Feedback | `score_feedback_message` | `score_feedback_message` | `snaptrash.insights` | `sustainability_score.py` — built string with tier + tip + comparisons |

---

## Databricks Tables

| Table | Schema | Purpose |
|-------|--------|---------|
| `snaptrash.scans` | CV team owned | Raw scan rows — one per photo upload |
| `analytics.synthetic_scans` | Dev only | Seeded by `seed_synthetic_scans.py` for local testing |
| `analytics.scans_unified` | VIEW | UNION ALL of scans + synthetic_scans; all analytics jobs read this |
| `snaptrash.insights` | Analytics writes | Per-restaurant rolling insight rows; score + forecasts UPDATEd in-place |
| `snaptrash.locality_agg` | Analytics writes | Per-ZIP aggregations; enzyme alert flag |
| `snaptrash.enzyme_alerts` | Analytics writes | Alert rows for notifier; `notified` flag |
| `analytics.gold_wcs_benchmark` | Reference | CA commercial waste % by material (WCS data) |
| `analytics.gold_sd_disposal_ts` | Reference | SD county per-capita disposal 2015–2019 |
| `analytics.gold_composting_routes_ca` | Reference | CA composting facilities with lat/lng/capacity |
| `analytics.gold_ca_composting_capacity` | Reference | Total CA network capacity (tons/yr) |
| `analytics.gold_sd_population` | Reference | SD county population by year |
| `analytics.gold_sd_zip_pop` | Reference | Per-ZIP Census ACS population |
| `analytics.gold_sd_restaurant_count` | Reference | SD restaurant count by ZIP |
| `analytics.gold_sd_commercial_benchmark` | Reference | SD commercial waste by material (tons) |
| `analytics.gold_food_prices` | Reference | USDA $/kg price map by food type |
| `analytics.gold_food_shelf_life` | Reference | USDA FoodKeeper shelf life days by food type |

---

## Analytics Jobs — Run Order

```bash
# 1. Seed synthetic scans (dev / demo only)
uv run --project apps/analytics python -m snaptrash_analytics.dev.seed_synthetic_scans

# 2. Rolling 7-day totals — writes base insight rows
uv run --project apps/analytics python -m snaptrash_analytics.aggregations.restaurant_rolling

# 3. Score signals + badge — UPDATEs sustainability_score, badge_tier, locality_percentile, etc.
uv run --project apps/analytics python -m snaptrash_analytics.aggregations.sustainability_score

# 4. Prophet forecasts — UPDATEs forecast_food_kg, forecast_dollar_waste, forecast_plastic_count
uv run --project apps/analytics python -m snaptrash_analytics.forecasting.prophet_forecast

# 5. Locality aggregation — writes locality_agg rows
uv run --project apps/analytics python -m snaptrash_analytics.aggregations.locality_agg

# 6. Threshold check (enzyme alerts)
uv run --project apps/analytics python -m snaptrash_analytics.aggregations.threshold_check
```

---

## What's Missing for Step 6 (Live Wiring)

### 1. Forecast chart series endpoint
`WEEKLY_SERIES` is hardcoded in `App.tsx`. Needs:
- New reader in `insights_reader.py` querying `scans_unified` grouped by date (last 7d actuals)
- Prophet per-day output stored or computed on demand
- FastAPI route `GET /api/weekly_series/:restaurant_id` returning `[{day, actual, forecast}]`

### 2. Frontend swap — mock → live
Replace in `App.tsx:11-52`:
```ts
// Current (mock)
const insights = MOCK_INSIGHTS;
const locality = MOCK_LOCALITY;

// Replace with:
const [insights, setInsights] = useState<Insight | null>(null);
const [locality, setLocality] = useState<LocalityAgg | null>(null);
// + useEffect with getInsights(RESTAURANT_ID) + getLocality(ZIP)
// + 45s polling interval (same pattern as old dashboard)
```

### 3. Analytics jobs must run after scans land
Real flow: scan submitted → `scans` table updated → trigger or schedule analytics jobs → `insights` updated → next frontend poll picks up new data.
Currently jobs are manual. Should be scheduled (Databricks Jobs or cron).
