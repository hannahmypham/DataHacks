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
  weekly_dollar_waste: number;
  forecast_next_week: number;
  locality_percentile: number;
  top_waste_category: string;
  recommendation: string;
  co2_avoided: number;
};

export type LocalityAgg = {
  zip: string;
  neighborhood: string;
  total_pet_kg: number;
  total_ps_count: number;
  harmful_count: number;
  active_restaurants: number;
  enzyme_alert: boolean;
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

export const getInsights = (restaurantId: string) =>
  get<Insight>(`/insights/${restaurantId}`);

export const getLocality = (zip: string) =>
  get<LocalityAgg>(`/locality/${zip}`);
