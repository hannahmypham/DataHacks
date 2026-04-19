import { useState, useMemo, useEffect } from "react";
import {
  TrendingUp,
  Calendar,
  AlertTriangle,
  Package,
  Gauge,
  Factory,
  MapPin,
} from "lucide-react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import type {
  ScanResponse,
  Insight,
  LocalityAgg,
  FoodItem,
  PlasticItem,
  LatestScan,
} from "@/lib/api";
import { getInsights, getLocality, getLatestScan } from "@/lib/api";

const RESTAURANT_ID = "demo-restaurant-001";
const ZIP = "92101";

/* ------------------------------------------------------------------ */
/* MOCK DATA — TODO: replace with live API call                        */
/* ------------------------------------------------------------------ */

// TODO: replace with live API call -> submitScan(payload)
const KG_TO_LBS = 2.20462;
const KM_TO_MI = 0.621371;

const mockScan: ScanResponse = {
  weekly_food_kg: 8.6,   // stored as kg internally; display in lbs
  forecast_food_kg: 10.2,
  weekly_plastic_count: 40,
  weekly_dollar_waste: 42.0,
  forecast_next_week: 48.0,
  top_waste_category: "Produce",
  food_items: [
    { name: "Lettuce & Greens", weight_kg: 3.1 },
    { name: "Tomatoes", weight_kg: 2.4 },
    { name: "Bread & Grains", weight_kg: 1.8 },
    { name: "Dairy", weight_kg: 1.3 },
  ] satisfies FoodItem[],
  plastic_items: [
    { name: "Single-use cups", count: 48 },
    { name: "Straws", count: 22, banned: true },
    { name: "Polystyrene", count: 14, harmful: true, banned: true },
    { name: "Cling film", count: 18, harmful: true },
    { name: "Cutlery", count: 24 },
  ] satisfies PlasticItem[],
};

// TODO: replace with live API call -> getInsights()
const mockInsight: Insight = {
  sustainability_score: 23.5,
  badge_tier: "Growing Tree",
  recommendation: "Reduce food waste volume",
  co2_avoided: 48.6,
  signal_1: 82,
  signal_2: 45,
  signal_3: 91,
  signal_4: 38,
  signal_5: 76,
  score_feedback_message: "You're outperforming most peers in your area.",
  nearest_facility_name: "Mission Valley Organics",
  nearest_facility_km: 2.4,  // stored as km; display in miles
};

// TODO: replace with live API call -> getLocality()
const mockLocality: LocalityAgg = {
  locality_percentile: 67,
  better_than_count: 4,
  zip_restaurant_count: 6,
};

// TODO: replace with live API call (7-day actual vs forecast time series, lbs)
const weeklySeries = [
  { day: "Mon", actual: 6.2, forecast: 6.5 },
  { day: "Tue", actual: 7.8, forecast: 7.2 },
  { day: "Wed", actual: 5.9, forecast: 6.8 },
  { day: "Thu", actual: 9.1, forecast: 8.5 },
  { day: "Fri", actual: 12.4, forecast: 11.8 },
  { day: "Sat", actual: 10.8, forecast: 11.2 },
  { day: "Sun", actual: 8.6, forecast: 9.0 },
];

// TODO: replace with live API call (next-week daily forecast, lbs)
const dailyForecast = [
  { day: "Mon", value: 9.2 },
  { day: "Tue", value: 10.5 },
  { day: "Wed", value: 11.8 },
  { day: "Thu", value: 13.2 },
  { day: "Fri", value: 14.5 },
  { day: "Sat", value: 12.9 },
  { day: "Sun", value: 11.3 },
];

const PLANT_STAGES: { tier: Insight["badge_tier"]; emoji: string; min: number; max: number }[] = [
  { tier: "Seedling", emoji: "🌱", min: 0, max: 39 },
  { tier: "Growing Plant", emoji: "🌿", min: 40, max: 59 },
  { tier: "Growing Tree", emoji: "🌲", min: 60, max: 79 },
  { tier: "Thriving Forest", emoji: "🌳", min: 80, max: 100 },
];

const SIGNAL_DETAILS: Record<
  string,
  { value: number; status: "good" | "warning" | "critical"; label: string; description: string; metric: string }
> = {
  S1: {
    value: mockInsight.signal_1,
    status: "good",
    label: "Waste Reduction",
    description: "Measures daily waste volume reduction vs. baseline",
    metric: "↓ 18% from baseline",
  },
  S2: {
    value: mockInsight.signal_2,
    status: "warning",
    label: "Separation Quality",
    description: "Quality of waste stream separation (recyclables, compost, trash)",
    metric: "45% correctly sorted",
  },
  S3: {
    value: mockInsight.signal_3,
    status: "good",
    label: "Compost Diversion",
    description: "Percentage of organic waste diverted to composting",
    metric: "91% diverted",
  },
  S4: {
    value: mockInsight.signal_4,
    status: "critical",
    label: "Plastic Reduction",
    description: "Single-use plastic items eliminated from waste stream",
    metric: "Only 38% reduction",
  },
  S5: {
    value: mockInsight.signal_5,
    status: "good",
    label: "Consistency",
    description: "Day-to-day consistency in sustainable waste practices",
    metric: "76% consistent",
  },
};

// Background images (Unsplash, same as Figma source)
const BG = {
  score:
    "url(https://images.unsplash.com/photo-1692232805863-0d3582b8353d?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&q=80&w=1920)",
  waste:
    "url(https://images.unsplash.com/photo-1523755292440-3a72acfa3c24?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&q=80&w=1920)",
  plastic:
    "url(https://images.unsplash.com/photo-1606037150583-fb842a55bae7?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&q=80&w=1920)",
  global:
    "url(https://images.unsplash.com/photo-1761212601062-448fdab7db68?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&q=80&w=1920)",
};

const PLASTIC_THRESHOLD = 50;

/* ------------------------------------------------------------------ */
/* Sub-components                                                      */
/* ------------------------------------------------------------------ */

function SectionShell({
  bg,
  overlayClass = "bg-gradient-to-b from-black/70 via-black/60 to-black/70",
  children,
}: {
  bg: string;
  overlayClass?: string;
  children: React.ReactNode;
}) {
  return (
    <section
      className="relative min-h-screen overflow-hidden py-20"
      style={{
        backgroundImage: bg,
        backgroundSize: "cover",
        backgroundPosition: "center",
        backgroundAttachment: "fixed",
      }}
    >
      <div className={`absolute inset-0 ${overlayClass}`} />
      <div className="relative z-10 mx-auto max-w-5xl px-6">{children}</div>
    </section>
  );
}

function LastScanCard({ scan }: { scan: LatestScan | null }) {
  // Databricks returns numeric columns as strings — coerce defensively
  const foodKg = scan ? Number(scan.food_kg) : 0;
  const dollarWastage = scan ? Number(scan.dollar_wastage) : 0;
  const plasticCount = scan ? Number(scan.plastic_count) : 0;
  const harmfulCount = scan ? Number(scan.harmful_plastic_count) : 0;
  const banCount = scan ? Number(scan.ban_flag_count) : 0;
  const ts = scan ? new Date(scan.timestamp) : null;
  const timeStr = ts
    ? ts.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    : null;
  const minsAgo = ts ? Math.max(0, Math.floor((Date.now() - ts.getTime()) / 60000)) : null;

  return (
    <div className="card-brand mb-8 border-signal-good/40">
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="relative flex h-3 w-3">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-signal-good opacity-75" />
            <span className="relative inline-flex h-3 w-3 rounded-full bg-signal-good" />
          </span>
          <span className="text-xs font-bold uppercase tracking-widest text-signal-good">
            Live Scan Feed
          </span>
        </div>
        {ts && (
          <span className="text-xs opacity-50">
            {timeStr} · {minsAgo === 0 ? "just now" : `${minsAgo}m ago`}
          </span>
        )}
      </div>

      {!scan ? (
        <p className="text-sm opacity-50">Waiting for scan…</p>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {/* Food detected */}
          <div>
            <div className="stat-label mb-2">Food Detected</div>
            {scan.food_items.length === 0 ? (
              <p className="text-xs opacity-50">None</p>
            ) : (
              <ul className="space-y-1">
                {scan.food_items.slice(0, 4).map((f, i) => (
                  <li key={i} className="flex items-center justify-between text-sm">
                    <span className="capitalize opacity-80">{f.type}</span>
                    <span className="font-bold tabular-nums">
                      {(Number(f.estimated_kg) * KG_TO_LBS).toFixed(2)} lbs
                    </span>
                  </li>
                ))}
              </ul>
            )}
            <div className="mt-2 border-t border-foreground/10 pt-2 text-sm">
              <span className="opacity-60">Total · </span>
              <span className="font-bold">{(foodKg * KG_TO_LBS).toFixed(2)} lbs</span>
              <span className="ml-3 font-bold text-signal-gold">
                ${dollarWastage.toFixed(2)}
              </span>
            </div>
          </div>

          {/* Plastic detected */}
          <div>
            <div className="stat-label mb-2">Plastic Detected</div>
            {scan.plastic_items.length === 0 ? (
              <p className="text-xs opacity-50">None</p>
            ) : (
              <ul className="space-y-1">
                {scan.plastic_items.slice(0, 4).map((p, i) => (
                  <li key={i} className="flex items-center justify-between text-sm">
                    <span className="capitalize opacity-80">{p.type}</span>
                    <span className="flex items-center gap-1">
                      {p.harmful && (
                        <span className="rounded bg-signal-bad/30 px-1 text-xs text-signal-bad">
                          harmful
                        </span>
                      )}
                      {p.recyclable && (
                        <span className="rounded bg-signal-good/30 px-1 text-xs text-signal-good">
                          ♻
                        </span>
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            )}
            <div className="mt-2 border-t border-foreground/10 pt-2 text-sm">
              <span className="opacity-60">Items · </span>
              <span className="font-bold">{plasticCount}</span>
              {harmfulCount > 0 && (
                <span className="ml-3 font-bold text-signal-bad">
                  {harmfulCount} harmful
                </span>
              )}
              {banCount > 0 && (
                <span className="ml-3 font-bold text-signal-bad">
                  {banCount} banned
                </span>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function ScoreSection({ lastScan }: { lastScan: LatestScan | null }) {
  const score = mockInsight.sustainability_score;
  const [hoveredSignal, setHoveredSignal] = useState<string | null>(null);
  const circumference = 2 * Math.PI * 140;
  const strokeDashoffset = circumference - (score / 100) * circumference;
  const scoreColor =
    score >= 70 ? "hsl(var(--signal-good))" : score >= 40 ? "hsl(var(--signal-warn))" : "hsl(var(--signal-bad))";
  const currentStage = PLANT_STAGES.findIndex((s) => score >= s.min && score <= s.max);

  const signalBg = (status: string) =>
    status === "good"
      ? "bg-signal-good border-signal-good"
      : status === "warning"
        ? "bg-signal-warn border-signal-warn"
        : "bg-signal-bad border-signal-bad";

  return (
    <SectionShell bg={BG.score}>
      <div className="mx-auto max-w-3xl">
        {/* Live scan feed */}
        <LastScanCard scan={lastScan} />

        {/* Plant growth */}
        <div className="mb-12">
          <h3 className="mb-6 text-center text-sm uppercase tracking-[0.25em] text-foreground/60">
            Growth Progression
          </h3>
          <div className="mb-8 flex justify-center gap-4 sm:gap-6">
            {PLANT_STAGES.map((stage, index) => {
              const active = index === currentStage;
              return (
                <div
                  key={stage.tier}
                  className={`flex flex-col items-center transition-all duration-300 ${
                    active ? "scale-110" : "scale-90 opacity-40"
                  }`}
                >
                  <div
                    className={`mb-2 flex h-20 w-20 items-center justify-center rounded-2xl border-2 transition-all ${
                      active
                        ? "border-signal-good bg-gradient-to-br from-signal-good/40 to-signal-info/30 shadow-lg shadow-signal-good/50"
                        : "border-foreground/10 bg-foreground/5"
                    }`}
                  >
                    <span className="text-4xl">{stage.emoji}</span>
                  </div>
                  <span className="text-center text-xs">{stage.tier}</span>
                </div>
              );
            })}
          </div>
        </div>

        {/* Score circle */}
        <div className="mb-10 flex flex-col items-center">
          <div className="relative mb-8">
            <svg width="320" height="320" className="-rotate-90 transform">
              <circle
                cx="160"
                cy="160"
                r="140"
                stroke="hsl(0 0% 100% / 0.15)"
                strokeWidth="20"
                fill="none"
              />
              <circle
                cx="160"
                cy="160"
                r="140"
                stroke={scoreColor}
                strokeWidth="20"
                fill="none"
                strokeLinecap="round"
                strokeDasharray={circumference}
                strokeDashoffset={strokeDashoffset}
                style={{ transition: "stroke-dashoffset 1.5s ease-out" }}
              />
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <div className="mb-2 text-8xl font-extrabold tracking-tight tabular-nums">{score}</div>
              <div className="text-lg uppercase tracking-wide text-foreground/70">Score</div>
            </div>
          </div>

          {/* Comparison */}
          <div className="mb-6 rounded-xl border border-signal-good/40 bg-signal-good/20 px-6 py-3 backdrop-blur-md">
            <p className="text-center text-sm">
              Better than{" "}
              <span className="font-bold">
                {mockLocality.better_than_count} of {mockLocality.zip_restaurant_count}
              </span>{" "}
              restaurants in Downtown SD
            </p>
          </div>

          {/* Recommendation */}
          <div className="mb-8 rounded-xl border border-signal-info/40 bg-signal-info/20 px-6 py-3 backdrop-blur-md">
            <p className="text-center text-sm font-semibold">💡 {mockInsight.recommendation}</p>
          </div>

          {/* Signal pills */}
          <div className="flex flex-wrap justify-center gap-3">
            {Object.entries(SIGNAL_DETAILS).map(([key, signal]) => (
              <div key={key} className="relative">
                <button
                  type="button"
                  onMouseEnter={() => setHoveredSignal(key)}
                  onMouseLeave={() => setHoveredSignal(null)}
                  onFocus={() => setHoveredSignal(key)}
                  onBlur={() => setHoveredSignal(null)}
                  className={`${signalBg(
                    signal.status,
                  )} cursor-pointer rounded-full border px-4 py-2 text-white transition-transform hover:scale-105`}
                >
                  <span className="font-bold">{key}</span> {signal.value}
                </button>
                {hoveredSignal === key && (
                  <div
                    className="absolute left-1/2 top-full z-20 mt-2 w-64 -translate-x-1/2 rounded-xl border border-brand-card-border/40 bg-brand-card/95 p-4 shadow-2xl backdrop-blur-xl"
                    style={{ boxShadow: "0 10px 40px hsl(0 0% 0% / 0.6)" }}
                  >
                    <h4 className="mb-1 text-sm font-bold text-brand-tan">{signal.label}</h4>
                    <p className="mb-2 text-xs opacity-80">{signal.description}</p>
                    <div className="rounded-lg border border-foreground/20 bg-foreground/10 px-3 py-1.5 text-xs">
                      {signal.metric}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>
    </SectionShell>
  );
}

function WasteSection() {
  const peakDay = useMemo(
    () => weeklySeries.reduce((a, b) => (b.actual > a.actual ? b : a)),
    [],
  );
  const peakLabel =
    { Mon: "Monday", Tue: "Tuesday", Wed: "Wednesday", Thu: "Thursday", Fri: "Friday", Sat: "Saturday", Sun: "Sunday" }[
      peakDay.day
    ] ?? peakDay.day;
  const avgDeviation =
    weeklySeries.reduce((s, r) => s + Math.abs(r.actual - r.forecast), 0) / weeklySeries.length;

  return (
    <SectionShell bg={BG.waste} overlayClass="bg-gradient-to-b from-black/75 via-black/65 to-black/75">
      <h2 className="section-title">🥗 Organic Waste Overview</h2>

      <div className="mb-8 grid gap-6 md:grid-cols-2">
        {/* Weekly Food Waste */}
        <div className="card-brand">
          <div className="stat-label">Weekly Food Waste</div>
          <div className="mb-2 flex items-baseline gap-3">
            <div className="stat-num-xl">{(mockScan.weekly_food_kg * KG_TO_LBS).toFixed(1)}</div>
            <div className="text-2xl opacity-70">lbs</div>
          </div>
          <div className="inline-block rounded-lg border border-signal-bad/50 bg-signal-bad/15 px-3 py-1.5">
            <span className="text-sm font-semibold text-signal-bad">+23% vs ZIP avg</span>
          </div>
        </div>

        {/* Weekly Dollar Waste */}
        <div className="card-brand">
          <div className="stat-label">Weekly Dollar Waste</div>
          <div className="mb-2 stat-num-xl">${mockScan.weekly_dollar_waste.toFixed(2)}</div>
          <div className="text-sm opacity-70">
            Projected{" "}
            <span className="font-bold text-signal-gold">
              ${mockScan.forecast_next_week.toFixed(2)}
            </span>{" "}
            next week
          </div>
        </div>

        {/* Peak Waste Day */}
        <div className="card-brand">
          <div className="flex items-start gap-4">
            <div className="icon-tile h-14 w-14 border-signal-good/40 bg-signal-good/20">
              <Calendar className="h-7 w-7 text-signal-good" />
            </div>
            <div className="flex-1">
              <div className="stat-label mb-2">Peak Waste Day</div>
              <div className="mb-1 text-3xl font-extrabold">{peakLabel}</div>
              <div className="text-lg font-semibold text-brand-tan">{peakDay.actual.toFixed(1)} lbs</div>
            </div>
          </div>
        </div>

        {/* Avg Deviation */}
        <div className="card-brand">
          <div className="flex items-start gap-4">
            <div className="icon-tile h-14 w-14 border-signal-info/40 bg-signal-info/20">
              <TrendingUp className="h-7 w-7 text-signal-info" />
            </div>
            <div className="flex-1">
              <div className="stat-label mb-2">Avg Deviation</div>
              <div className="mb-1 text-3xl font-extrabold">±{avgDeviation.toFixed(1)}</div>
              <div className="text-sm opacity-70">lbs from forecast</div>
            </div>
          </div>
        </div>
      </div>

      {/* Chart */}
      <div className="card-brand">
        <h3 className="mb-6 text-lg font-bold uppercase tracking-wide text-brand-tan">
          7-Day Actual vs Forecasted
        </h3>
        <ResponsiveContainer width="100%" height={300}>
          <AreaChart data={weeklySeries} margin={{ top: 10, right: 20, left: 0, bottom: 10 }}>
            <defs>
              <linearGradient id="colorActual" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="hsl(var(--signal-good))" stopOpacity={0.5} />
                <stop offset="95%" stopColor="hsl(var(--signal-good))" stopOpacity={0} />
              </linearGradient>
              <linearGradient id="colorForecast" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="hsl(var(--signal-info))" stopOpacity={0.4} />
                <stop offset="95%" stopColor="hsl(var(--signal-info))" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--brand-card-border) / 0.2)" />
            <XAxis
              dataKey="day"
              tick={{ fill: "hsl(var(--brand-tan) / 0.8)", fontSize: 12 }}
              axisLine={{ stroke: "hsl(var(--brand-card-border) / 0.4)" }}
            />
            <YAxis
              tick={{ fill: "hsl(var(--brand-tan) / 0.8)", fontSize: 12 }}
              axisLine={{ stroke: "hsl(var(--brand-card-border) / 0.4)" }}
              label={{
                value: "lbs",
                angle: -90,
                position: "insideLeft",
                fill: "hsl(var(--brand-tan) / 0.8)",
              }}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "hsl(var(--brand-card) / 0.95)",
                border: "1px solid hsl(var(--brand-card-border) / 0.4)",
                borderRadius: "8px",
              }}
              labelStyle={{ color: "hsl(var(--foreground))" }}
            />
            <Area
              type="monotone"
              dataKey="actual"
              stroke="hsl(var(--signal-good))"
              strokeWidth={3}
              fill="url(#colorActual)"
              name="Actual"
            />
            <Area
              type="monotone"
              dataKey="forecast"
              stroke="hsl(var(--signal-info))"
              strokeWidth={3}
              strokeDasharray="8 4"
              fill="url(#colorForecast)"
              name="Forecast"
            />
          </AreaChart>
        </ResponsiveContainer>
        <div className="mt-4 flex justify-center gap-6">
          <div className="flex items-center gap-2">
            <div className="h-1 w-8 bg-signal-good" />
            <span className="text-xs opacity-70">Actual</span>
          </div>
          <div className="flex items-center gap-2">
            <div
              className="h-1 w-8"
              style={{
                backgroundImage:
                  "repeating-linear-gradient(90deg, hsl(var(--signal-info)), hsl(var(--signal-info)) 4px, transparent 4px, transparent 8px)",
              }}
            />
            <span className="text-xs opacity-70">Forecast</span>
          </div>
        </div>
      </div>
    </SectionShell>
  );
}

function PlasticSection() {
  const harmfulCount = mockScan.plastic_items.filter((p) => p.harmful).length;
  const bannedCount = mockScan.plastic_items.filter((p) => p.banned).length;
  const currentItems = mockScan.weekly_plastic_count;
  const isAbove = currentItems > PLASTIC_THRESHOLD;
  const pct = Math.min(100, (currentItems / PLASTIC_THRESHOLD) * 100);

  return (
    <SectionShell bg={BG.plastic} overlayClass="bg-gradient-to-b from-black/80 via-black/75 to-black/80">
      <h2 className="section-title">♻️ Plastic Waste Analysis</h2>

      <div className="mb-6 grid gap-6 md:grid-cols-2">
        {/* Volume of Plastic */}
        <div className="card-brand">
          <div className="stat-label">Volume of Plastic</div>
          <div className="mb-2 flex items-baseline gap-3">
            <div className="stat-num-xl">3.2</div>
            <div className="text-2xl opacity-70">lbs/week</div>
          </div>
          <div className="text-sm opacity-70">32% of total waste stream</div>
        </div>

        {/* Items per Week */}
        <div className="card-brand">
          <div className="flex items-start gap-4">
            <div className="icon-tile h-14 w-14 border-signal-info/40 bg-signal-info/20">
              <Package className="h-7 w-7 text-signal-info" />
            </div>
            <div className="flex-1">
              <div className="stat-label mb-2">Items/Week</div>
              <div className="mb-1 text-5xl font-extrabold tabular-nums">{currentItems}</div>
              <div className="text-sm opacity-70">plastic items discarded</div>
            </div>
          </div>
        </div>
      </div>

      {/* Harmful & Banned */}
      <div className="card-brand-danger mb-6">
        <div className="flex items-start gap-6">
          <div className="icon-tile h-20 w-20 border-2 border-signal-bad/60 bg-signal-bad/20">
            <AlertTriangle className="h-10 w-10 text-signal-bad" />
          </div>
          <div className="flex-1">
            <h3 className="mb-4 text-2xl font-bold uppercase tracking-wide">
              Harmful & Banned Plastics
            </h3>
            <div className="grid gap-6 sm:grid-cols-2">
              <div>
                <div className="stat-label mb-1">Harmful Plastics</div>
                <div className="text-4xl font-extrabold tabular-nums text-signal-gold">
                  {harmfulCount}
                </div>
                <div className="mt-1 text-sm opacity-70">items detected</div>
              </div>
              <div>
                <div className="stat-label mb-1">Banned Items (SB 54)</div>
                <div className="text-4xl font-extrabold tabular-nums text-signal-bad">
                  {bannedCount}
                </div>
                <div className="mt-1 text-sm opacity-70">items detected</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Threshold */}
      <div className={isAbove ? "card-brand-danger" : "card-brand"}>
        <div className="mb-6 flex items-start gap-4">
          <div
            className={`icon-tile h-14 w-14 ${
              isAbove ? "border-signal-bad/60 bg-signal-bad/20" : "border-signal-good/40 bg-signal-good/20"
            }`}
          >
            <Gauge className={`h-7 w-7 ${isAbove ? "text-signal-bad" : "text-signal-good"}`} />
          </div>
          <div className="flex-1">
            <div className="stat-label mb-2">Weekly Threshold Monitor</div>
            <div className="mb-1 flex items-baseline gap-3">
              <div className="text-4xl font-extrabold tabular-nums">{currentItems}</div>
              <div className="text-xl opacity-70">/ {PLASTIC_THRESHOLD} items</div>
            </div>
            <div
              className={`text-sm font-semibold ${isAbove ? "text-signal-bad" : "text-signal-good"}`}
            >
              {isAbove
                ? `⚠️ ${currentItems - PLASTIC_THRESHOLD} items over threshold`
                : "✓ Within safe threshold"}
            </div>
          </div>
        </div>

        <div className="relative">
          <div className="h-6 overflow-hidden rounded-full border border-foreground/20 bg-foreground/10">
            <div
              className={`h-full transition-all duration-1000 ease-out ${
                isAbove ? "bg-signal-bad" : "bg-signal-good"
              }`}
              style={{ width: `${pct}%` }}
            />
          </div>
          <div className="absolute bottom-0 top-0 w-1 bg-foreground" style={{ left: "100%", transform: "translateX(-50%)" }}>
            <div className="absolute -top-6 left-1/2 -translate-x-1/2 whitespace-nowrap text-xs opacity-70">
              Limit
            </div>
          </div>
        </div>

        <div className="mt-3 flex justify-between text-xs opacity-60">
          <span>0</span>
          <span>{PLASTIC_THRESHOLD} items</span>
        </div>
      </div>
    </SectionShell>
  );
}

function GlobalSection() {
  const totalForecast = dailyForecast.reduce((a, b) => a + b.value, 0);

  return (
    <SectionShell bg={BG.global} overlayClass="bg-gradient-to-b from-black/85 via-black/80 to-black/90">
      <h2 className="section-title">🌍 Local Context & Forecast</h2>

      <div className="mb-6 grid gap-6 md:grid-cols-2">
        {/* Local Ranking */}
        <div className="card-brand">
          <div className="stat-label mb-6">Local Ranking</div>
          <div className="mb-6">
            <div className="mb-2 flex items-baseline gap-2">
              <div className="stat-num-xl">{mockLocality.better_than_count}</div>
              <div className="text-2xl opacity-70">of {mockLocality.zip_restaurant_count}</div>
            </div>
            <div className="text-sm opacity-70">in ZIP 92101</div>
          </div>
          <div className="flex gap-2">
            {Array.from({ length: mockLocality.zip_restaurant_count }).map((_, i) => (
              <div
                key={i}
                className={`h-3 flex-1 rounded-full ${
                  i + 1 === mockLocality.better_than_count
                    ? "bg-signal-info"
                    : i + 1 < mockLocality.better_than_count
                      ? "bg-signal-good"
                      : "bg-foreground/20"
                }`}
              />
            ))}
          </div>
        </div>

        {/* Current Food Waste */}
        <div className="card-brand">
          <div className="stat-label">Current Food Waste</div>
          <div className="mb-2 flex items-baseline gap-3">
            <div className="stat-num-xl">{(mockScan.weekly_food_kg * KG_TO_LBS).toFixed(1)}</div>
            <div className="text-2xl opacity-70">lbs/week</div>
          </div>
          <div className="inline-block rounded-lg border border-signal-orange/50 bg-signal-orange/15 px-3 py-1.5">
            <span className="text-sm font-semibold text-signal-orange">Trending upward</span>
          </div>
        </div>

        {/* Compost Shelf Life */}
        <div className="card-brand">
          <div className="stat-label">Compost Shelf Life</div>
          <div className="mb-2 flex items-baseline gap-3">
            <div className="stat-num-xl">4-6</div>
            <div className="text-2xl opacity-70">months</div>
          </div>
          <div className="text-sm opacity-70">Average curing time for compost</div>
        </div>

        {/* Next Week Forecast */}
        <div className="card-brand">
          <div className="flex items-start gap-4">
            <div className="icon-tile h-14 w-14 border-signal-warn/40 bg-signal-warn/20">
              <TrendingUp className="h-7 w-7 text-signal-warn" />
            </div>
            <div className="flex-1">
              <div className="stat-label mb-2">Next Week Forecast</div>
              <div className="mb-1 text-5xl font-extrabold tabular-nums">
                {totalForecast.toFixed(1)}
              </div>
              <div className="text-sm opacity-70">lbs projected</div>
            </div>
          </div>
        </div>
      </div>

      {/* Daily Forecast Breakdown */}
      <div className="card-brand mb-6">
        <h3 className="mb-6 text-lg font-bold uppercase tracking-wide text-brand-tan">
          Daily Forecast Breakdown
        </h3>
        <div className="space-y-3">
          {dailyForecast.map((d) => (
            <div key={d.day} className="flex items-center gap-4">
              <div className="w-16 text-sm opacity-70">{d.day}</div>
              <div className="h-8 flex-1 overflow-hidden rounded-lg border border-foreground/20 bg-foreground/10">
                <div
                  className="h-full bg-gradient-to-r from-signal-warn to-signal-amber transition-all duration-1000 ease-out"
                  style={{ width: `${(d.value / 15) * 100}%` }}
                />
              </div>
              <div className="w-16 text-right font-bold tabular-nums">{d.value} lbs</div>
            </div>
          ))}
        </div>
      </div>

      {/* Nearest Facility */}
      <div className="card-brand-success">
        <div className="mb-6 flex items-start gap-6">
          <div className="icon-tile h-20 w-20 border-2 border-signal-good/60 bg-signal-good/20">
            <Factory className="h-10 w-10 text-signal-good" />
          </div>
          <div className="flex-1">
            <h3 className="mb-2 text-2xl font-bold uppercase tracking-wide">
              Nearest Composting Facility
            </h3>
            <a
              href={`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(mockInsight.nearest_facility_name ?? "composting facility")}`}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 text-xl text-signal-good underline-offset-4 hover:underline"
            >
              {mockInsight.nearest_facility_name} ↗
            </a>
            <p className="mt-1 text-xs opacity-50">Tap for directions</p>
          </div>
        </div>
        <div className="grid gap-6 border-t border-foreground/20 pt-6 sm:grid-cols-2">
          <div>
            <div className="stat-label mb-2 flex items-center gap-1.5">
              <MapPin className="h-3 w-3" />
              Distance
            </div>
            <div className="flex items-baseline gap-2">
              <div className="text-4xl font-extrabold tabular-nums">
                {(mockInsight.nearest_facility_km * KM_TO_MI).toFixed(1)}
              </div>
              <div className="text-xl opacity-70">mi</div>
            </div>
          </div>
          <div>
            <div className="stat-label mb-2">Capacity</div>
            <div className="flex items-baseline gap-2">
              <div className="text-4xl font-extrabold tabular-nums">850</div>
              <div className="text-xl opacity-70">tons/mo</div>
            </div>
          </div>
        </div>
      </div>
    </SectionShell>
  );
}

/* ------------------------------------------------------------------ */
/* Page                                                                */
/* ------------------------------------------------------------------ */

const Index = () => {
  const [, setTick] = useState(0);
  const [lastScan, setLastScan] = useState<LatestScan | null>(null);

  // Insights + locality: refresh every 30s
  useEffect(() => {
    const refresh = () => {
      Promise.all([
        getInsights(RESTAURANT_ID).catch(() => null),
        getLocality(ZIP).catch(() => null),
      ]).then(([insight, locality]) => {
        if (insight) {
          Object.assign(mockInsight, insight);
          // Databricks returns numbers as strings — coerce all numeric fields
          mockInsight.sustainability_score = Number(mockInsight.sustainability_score);
          mockInsight.signal_1 = Number(mockInsight.signal_1);
          mockInsight.signal_2 = Number(mockInsight.signal_2);
          mockInsight.signal_3 = Number(mockInsight.signal_3);
          mockInsight.signal_4 = Number(mockInsight.signal_4);
          mockInsight.signal_5 = Number(mockInsight.signal_5);
          mockInsight.co2_avoided = Number(mockInsight.co2_avoided);
          mockInsight.nearest_facility_km = Number(mockInsight.nearest_facility_km);
          // Push weekly totals into mockScan (coerced to number)
          if (insight.weekly_food_kg != null) mockScan.weekly_food_kg = Number(insight.weekly_food_kg);
          if (insight.weekly_dollar_waste != null) mockScan.weekly_dollar_waste = Number(insight.weekly_dollar_waste);
          if (insight.weekly_plastic_count != null) mockScan.weekly_plastic_count = Number(insight.weekly_plastic_count);
          if (insight.forecast_food_kg != null) mockScan.forecast_food_kg = Number(insight.forecast_food_kg);
          if (insight.forecast_dollar_waste != null) mockScan.forecast_next_week = Number(insight.forecast_dollar_waste);
        }
        if (locality) {
          Object.assign(mockLocality, locality);
          mockLocality.locality_percentile = Number(mockLocality.locality_percentile);
          mockLocality.better_than_count = Number(mockLocality.better_than_count);
          mockLocality.zip_restaurant_count = Number(mockLocality.zip_restaurant_count);
        }
        setTick(t => t + 1);
      });
    };
    refresh();
    const interval = setInterval(refresh, 30000);
    return () => clearInterval(interval);
  }, []);

  // Latest scan: refresh every 10s for near-instant feedback
  useEffect(() => {
    const fetchLatest = () => {
      getLatestScan(RESTAURANT_ID)
        .then(setLastScan)
        .catch(() => {});
    };
    fetchLatest();
    const interval = setInterval(fetchLatest, 10000);
    return () => clearInterval(interval);
  }, []);

  return (
    <main className="min-h-screen bg-brand-bg text-foreground">
      <h1 className="sr-only">Sustainability Dashboard — weekly impact overview</h1>
      <ScoreSection lastScan={lastScan} />
      <WasteSection />
      <PlasticSection />
      <GlobalSection />
      <footer className="bg-brand-bg py-6 text-center text-xs text-foreground/50">
        SnapTrash · Waste Intelligence Dashboard
      </footer>
    </main>
  );
};

export default Index;
