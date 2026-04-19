/**
 * Typed wrappers around the FastAPI ingestion + analytics endpoints.
 * All requests go through Vite's /api proxy → http://localhost:8000.
 */

const BASE = "/api";

async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${BASE}${path}`);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

async function postForm<T>(path: string, form: FormData): Promise<T> {
  const r = await fetch(`${BASE}${path}`, { method: "POST", body: form });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

// ---- types (mirror snaptrash_common.schemas) ----
export type FoodItem = {
  type: string;
  decay_stage: number;
  estimated_kg: number;
  contaminated: boolean;
  compostable: boolean;
  shelf_life_remaining_days?: number;
  dollar_value?: number;
  co2_kg?: number;
};

export type PlasticItem = {
  type: string;
  resin_code?: number;
  polymer_type?: string;
  status?: string;
  recyclable?: boolean;
  harmful?: boolean;
  alert?: string;
};

export type ScanResponse = {
  scan_id: string;
  s3_url: string;
  food_items: FoodItem[];
  plastic_items: PlasticItem[];
  totals: Record<string, unknown>;
};

export type Insight = {
  restaurant_id: string;
  computed_at?: string;
  weekly_dollar_waste: number;
  weekly_food_kg?: number;
  weekly_plastic_count?: number;
  forecast_dollar_waste?: number;
  forecast_food_kg?: number;
  forecast_plastic_count?: number;
  locality_percentile: number;
  locality_percentile_pct?: number;
  better_than_count?: number;
  zip_restaurant_count?: number;
  sustainability_score?: number;
  badge_tier?: string;
  tier_emoji?: string;
  score_feedback_message?: string;
  top_waste_category: string;
  peak_waste_day?: string;
  peak_waste_day_kg?: number;
  recommendation: string;
  co2_avoided: number;
  shelf_life_min_days?: number;
  shelf_life_avg_days?: number;
  at_risk_kg_24h?: number;
  nearest_facility_name?: string;
  nearest_facility_km?: number;
  harmful_plastic_count?: number;
  ban_flag_count?: number;
  signal_1?: number;
  signal_2?: number;
  signal_3?: number;
  signal_4?: number;
  signal_5?: number;
  signals?: Record<string, any>;
  enzyme_alert?: boolean;
};

export type LocalityAgg = {
  zip: string;
  neighborhood: string;
  computed_at?: string;
  total_pet_kg: number;
  total_ps_count: number;
  harmful_count: number;
  active_restaurants: number;
  enzyme_alert: boolean;
  food_waste_per_capita_kg?: number;
  avg_sustainability_score?: number;
  score_feedback_message?: string;
};

export type LatestScan = {
  scan_id: string;
  timestamp: string;
  food_kg: number;
  dollar_wastage: number;
  plastic_count: number;
  harmful_plastic_count: number;
  ban_flag_count: number;
  food_items: FoodItem[];
  plastic_items: PlasticItem[];
};

// ---- endpoints ----
export const health = () => get<{ status: string }>("/health");

export const submitScan = (file: File, restaurantId: string, zip: string, neighborhood = "") => {
  const f = new FormData();
  f.append("image", file);
  f.append("restaurant_id", restaurantId);
  f.append("zip", zip);
  f.append("neighborhood", neighborhood);
  return postForm<ScanResponse>("/scan", f);
};

export const getLatestScan = (restaurantId: string) =>
  get<LatestScan>(`/scan/latest/${restaurantId}`);

export const getInsights = (restaurantId: string) =>
  get<Insight>(`/insights/${restaurantId}`);

export const getLocality = (zip: string) =>
  get<LocalityAgg>(`/locality/${zip}`);

export type DayActual = { day: string; actual: number };

export const getWeeklySeries = (restaurantId: string) =>
  get<DayActual[]>(`/weekly-series/${restaurantId}`);
