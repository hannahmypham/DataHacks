import { useState, useMemo, useEffect } from "react";
import {
  Calendar,
  AlertTriangle,
  Package,
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
  Insight,
  LocalityAgg,
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

// Local mock type — holds display fields not in ScanResponse API type
const mockScan = {
  weekly_food_kg: 27.6,
  forecast_food_kg: 27.7,
  weekly_plastic_count: 25,
  weekly_dollar_waste: 42.0,
  forecast_next_week: 48.0,
  plastic_items: [
    { name: "Single-use cups", harmful: false, banned: false },
    { name: "Straws", harmful: false, banned: true },
    { name: "Polystyrene", harmful: true, banned: true },
    { name: "Cling film", harmful: true, banned: false },
    { name: "Cutlery", harmful: false, banned: false },
  ],
};

const mockInsight: Insight = {
  restaurant_id: RESTAURANT_ID,
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
  nearest_facility_km: 2.4,
  weekly_dollar_waste: 42.0,
  top_waste_category: "Produce",
  locality_percentile: 0.67,
  better_than_count: 4,
  zip_restaurant_count: 6,
};

const mockLocality: LocalityAgg = {
  zip: ZIP,
  neighborhood: "Downtown San Diego",
  total_pet_kg: 0,
  total_ps_count: 0,
  harmful_count: 0,
  active_restaurants: 6,
  enzyme_alert: false,
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

const SCORE_BANDS = [
  { label: "Waste Crisis",        emoji: "🗑️", desc: "Urgent intervention needed",    min: 0,  max: 39  },
  { label: "Reducing Impact",     emoji: "🌱", desc: "Making meaningful progress",     min: 40, max: 59  },
  { label: "Green Operator",      emoji: "♻️", desc: "Solid sustainable practices",   min: 60, max: 79  },
  { label: "Zero Waste Champion", emoji: "🌍", desc: "Setting the industry standard", min: 80, max: 100 },
];


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
  const score = mockInsight.sustainability_score ?? 0;
  const circumference = 2 * Math.PI * 140;
  const strokeDashoffset = circumference - (score / 100) * circumference;
  const scoreColor =
    score >= 70 ? "hsl(var(--signal-good))" : score >= 40 ? "hsl(var(--signal-warn))" : "hsl(var(--signal-bad))";
  const currentBand = SCORE_BANDS.findIndex((b) => score >= b.min && score <= b.max);
  const foodTrending = mockScan.weekly_food_kg > mockScan.forecast_food_kg;

  return (
    <SectionShell bg={BG.score}>
      <div className="mx-auto max-w-3xl">
        {/* Live scan feed */}
        <LastScanCard scan={lastScan} />

        {/* Score bands */}
        <div className="mb-12">
          <h3 className="mb-6 text-center text-sm uppercase tracking-[0.25em] text-foreground/60">
            Impact Rating
          </h3>
          <div className="mb-8 flex justify-center gap-4 sm:gap-6">
            {SCORE_BANDS.map((band, index) => {
              const active = index === currentBand;
              return (
                <div
                  key={band.label}
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
                    <span className="text-4xl">{band.emoji}</span>
                  </div>
                  <span className="text-center text-xs font-semibold">{band.label}</span>
                  {active && <span className="mt-1 text-center text-xs opacity-60">{band.desc}</span>}
                </div>
              );
            })}
          </div>
        </div>

        {/* Score circle */}
        <div className="mb-10 flex flex-col items-center">
          <div className="relative mb-8">
            <svg width="320" height="320" className="-rotate-90 transform">
              <circle cx="160" cy="160" r="140" stroke="hsl(0 0% 100% / 0.15)" strokeWidth="20" fill="none" />
              <circle
                cx="160" cy="160" r="140"
                stroke={scoreColor} strokeWidth="20" fill="none" strokeLinecap="round"
                strokeDasharray={circumference} strokeDashoffset={strokeDashoffset}
                style={{ transition: "stroke-dashoffset 1.5s ease-out" }}
              />
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <div className="mb-2 text-8xl font-extrabold tracking-tight tabular-nums">{score}</div>
              <div className="text-lg uppercase tracking-wide text-foreground/70">Score</div>
            </div>
          </div>

          {/* Recommendation */}
          <div className="mb-8 w-full rounded-xl border border-signal-info/40 bg-signal-info/20 px-4 py-2.5 backdrop-blur-md">
            <p className="truncate text-center text-sm font-semibold">
              💡 AI-powered waste tracking — scan, analyze, and reduce your footprint
            </p>
          </div>

          {/* Local ranking + food waste row */}
          <div className="grid w-full gap-4 sm:grid-cols-2">
            {/* Local Ranking */}
            {(() => {
              const better = mockInsight.better_than_count ?? 4;
              const total = mockInsight.zip_restaurant_count ?? 6;
              const rank = Math.max(1, total - better);
              const medal = rank === 1 ? "🥇" : rank === 2 ? "🥈" : rank === 3 ? "🥉" : null;
              const cardStyle =
                rank === 1
                  ? "card-brand border-yellow-400/60 bg-yellow-400/10"
                  : rank === 2
                    ? "card-brand border-gray-300/50 bg-gray-300/10"
                    : rank === 3
                      ? "card-brand border-amber-600/50 bg-amber-600/10"
                      : "card-brand";
              return (
                <div className={cardStyle}>
                  <div className="mb-3 flex items-center justify-between">
                    <div className="stat-label">Local Ranking</div>
                    {medal && <span className="text-3xl">{medal}</span>}
                  </div>
                  <div className="mb-1 flex items-baseline gap-2">
                    <div className="stat-num-xl">#{rank}</div>
                    <div className="text-xl opacity-70">of {total}</div>
                  </div>
                  <div className="mb-3 text-xs opacity-60">restaurants in ZIP 92101</div>
                  <div className="flex gap-1.5">
                    {Array.from({ length: total }).map((_, i) => (
                      <div
                        key={i}
                        className={`h-2 flex-1 rounded-full ${
                          i + 1 === rank
                            ? rank === 1 ? "bg-yellow-400" : rank === 2 ? "bg-gray-300" : rank === 3 ? "bg-amber-600" : "bg-signal-info"
                            : i + 1 < rank
                              ? "bg-signal-info"
                              : "bg-foreground/20"
                        }`}
                      />
                    ))}
                  </div>
                </div>
              );
            })()}

            {/* Current Food Waste + trend */}
            <div className="card-brand">
              <div className="stat-label mb-3">Food Waste This Week</div>
              <div className="mb-2 flex items-baseline gap-2">
                <div className="stat-num-xl">{(mockScan.weekly_food_kg * KG_TO_LBS).toFixed(1)}</div>
                <div className="text-xl opacity-70">lbs</div>
                <span className={`ml-1 text-2xl font-bold ${foodTrending ? "text-signal-bad" : "text-signal-good"}`}>
                  {foodTrending ? "↑" : "↓"}
                </span>
              </div>
              <div className={`text-sm font-semibold ${foodTrending ? "text-signal-bad" : "text-signal-good"}`}>
                {foodTrending ? "Above forecast — review inventory" : "Below forecast — great control"}
              </div>
            </div>
          </div>
        </div>
      </div>
    </SectionShell>
  );
}

function WasteSection() {
  const foodThreshold = 80;
  const peakDay = useMemo(
    () => weeklySeries.reduce((a, b) => (b.actual > a.actual ? b : a)),
    [],
  );
  const peakLabel =
    { Mon: "Monday", Tue: "Tuesday", Wed: "Wednesday", Thu: "Thursday", Fri: "Friday", Sat: "Saturday", Sun: "Sunday" }[
      peakDay.day
    ] ?? peakDay.day;

  const foodLbs = mockScan.weekly_food_kg * KG_TO_LBS;
  const foodTrending = mockScan.weekly_food_kg > mockScan.forecast_food_kg;
  const foodAboveThreshold = foodLbs > foodThreshold;
  const foodThresholdPct = Math.min(100, (foodLbs / foodThreshold) * 100);

  const thresholdEmoji = foodAboveThreshold ? "🚨" : foodThresholdPct > 75 ? "⚠️" : "✅";

  return (
    <SectionShell bg={BG.waste} overlayClass="bg-gradient-to-b from-black/75 via-black/65 to-black/75">
      <h2 className="section-title">🥗 Organic Waste Overview</h2>

      <div className="mb-8 grid gap-6 md:grid-cols-2">
        {/* Weekly Food Waste */}
        <div className="card-brand">
          <div className="stat-label">Weekly Food Waste</div>
          <div className="mb-2 flex items-baseline gap-3">
            <div className="stat-num-xl">{foodLbs.toFixed(1)}</div>
            <div className="text-2xl opacity-70">lbs</div>
            <span className={`text-2xl font-bold ${foodTrending ? "text-signal-bad" : "text-signal-good"}`}>
              {foodTrending ? "↑" : "↓"}
            </span>
          </div>
          <div className={`text-sm font-semibold ${foodTrending ? "text-signal-bad" : "text-signal-good"}`}>
            {foodTrending ? "Trending up vs forecast" : "Trending down vs forecast"}
          </div>
        </div>

        {/* Weekly Dollar Waste */}
        <div className="card-brand">
          <div className="stat-label">Weekly Dollar Waste</div>
          <div className="mb-2 flex items-baseline gap-3">
            <div className="stat-num-xl">${mockScan.weekly_dollar_waste.toFixed(2)}</div>
          </div>
          <div className="text-sm font-semibold opacity-60">
            Estimated food cost lost this week
          </div>
        </div>

        {/* Peak Waste Day */}
        <div className="card-brand">
          <div className="flex flex-col items-center justify-center text-center py-2">
            <div className="icon-tile mb-3 h-14 w-14 border-signal-good/40 bg-signal-good/20">
              <Calendar className="h-7 w-7 text-signal-good" />
            </div>
            <div className="stat-label mb-2">Peak Waste Day</div>
            <div className="mb-1 text-5xl font-extrabold">{peakLabel}</div>
            <div className="text-lg font-semibold text-brand-tan">{peakDay.actual.toFixed(1)} lbs</div>
          </div>
        </div>

        {/* Food Wastage Threshold */}
        <div className={foodAboveThreshold ? "card-brand-danger" : "card-brand"}>
          <div className="mb-4 flex items-center justify-between">
            <div className="stat-label">Food Wastage Threshold</div>
            <span className="text-2xl">{thresholdEmoji}</span>
          </div>
          <div className="mb-1 flex items-baseline gap-2">
            <span className="text-4xl font-extrabold tabular-nums">{foodLbs.toFixed(1)}</span>
            <span className="opacity-70">/ {foodThreshold} lbs</span>
          </div>
          <div className={`mb-4 text-sm font-semibold ${foodAboveThreshold ? "text-signal-bad" : "text-signal-good"}`}>
            {foodAboveThreshold
              ? `${(foodLbs - foodThreshold).toFixed(1)} lbs over your limit`
              : `${(foodThreshold - foodLbs).toFixed(1)} lbs below your limit`}
          </div>
          <div className="mb-2 h-3 overflow-hidden rounded-full bg-foreground/10">
            <div
              className={`h-full rounded-full transition-all duration-700 ${foodAboveThreshold ? "bg-signal-bad" : "bg-signal-good"}`}
              style={{ width: `${foodThresholdPct}%` }}
            />
          </div>
          <div className="mt-2 flex justify-between text-xs opacity-50">
            <span>0 lbs</span>
            <span>Limit: {foodThreshold} lbs/week</span>
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
  const plasticThreshold = 50;
  const harmfulItems = mockScan.plastic_items.filter((p) => p.harmful);
  const bannedItems = mockScan.plastic_items.filter((p) => p.banned);
  const currentItems = mockScan.weekly_plastic_count;
  const itemsPerDay = (currentItems / 7).toFixed(1);
  const volumeTrending = true; // mock: plastic volume trending up
  const itemsTrending = true;  // mock: item count trending up
  const isAbove = currentItems > plasticThreshold;
  const pct = Math.min(100, (currentItems / plasticThreshold) * 100);
  const thresholdEmoji = isAbove ? "🚨" : pct > 75 ? "⚠️" : pct > 50 ? "😐" : "✅";

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
            <span className={`text-2xl font-bold ${volumeTrending ? "text-signal-bad" : "text-signal-good"}`}>{volumeTrending ? "↑" : "↓"}</span>
          </div>
          <div className={`text-sm font-semibold ${volumeTrending ? "text-signal-bad" : "text-signal-good"}`}>
            {volumeTrending ? "Volume increasing this week" : "Volume decreasing this week"}
          </div>
        </div>

        {/* Items per Day */}
        <div className="card-brand">
          <div className="flex items-start gap-4">
            <div className="icon-tile h-14 w-14 border-signal-info/40 bg-signal-info/20">
              <Package className="h-7 w-7 text-signal-info" />
            </div>
            <div className="flex-1">
              <div className="stat-label mb-2">Items/Day</div>
              <div className="mb-1 flex items-baseline gap-2">
                <div className="text-5xl font-extrabold tabular-nums">{itemsPerDay}</div>
                <span className={`text-2xl font-bold ${itemsTrending ? "text-signal-bad" : "text-signal-good"}`}>{itemsTrending ? "↑" : "↓"}</span>
              </div>
              <div className={`text-sm font-semibold ${itemsTrending ? "text-signal-bad" : "text-signal-good"}`}>
                {itemsTrending ? "Daily rate rising" : "Daily rate falling"}
              </div>
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
                <div className="stat-label mb-2">Harmful Plastics</div>
                <div className="mb-2 text-4xl font-extrabold tabular-nums text-signal-gold">
                  {harmfulItems.length}
                </div>
                <ul className="space-y-1">
                  {harmfulItems.map((p, i) => (
                    <li key={i} className="flex items-center gap-2 text-xs">
                      <span className="h-1.5 w-1.5 rounded-full bg-signal-gold" />
                      <span className="capitalize opacity-80">{p.name}</span>
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <div className="stat-label mb-2">Banned Items (SB 54)</div>
                <div className="mb-2 text-4xl font-extrabold tabular-nums text-signal-bad">
                  {bannedItems.length}
                </div>
                <ul className="space-y-1">
                  {bannedItems.map((p, i) => (
                    <li key={i} className="flex items-center gap-2 text-xs">
                      <span className="h-1.5 w-1.5 rounded-full bg-signal-bad" />
                      <span className="capitalize opacity-80">{p.name}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Interactive Threshold */}
      <div className={isAbove ? "card-brand-danger" : "card-brand"}>
        <div className="mb-4 flex items-center justify-between">
          <div className="stat-label">Weekly Plastic Limit</div>
          <span className="text-3xl">{thresholdEmoji}</span>
        </div>
        <div className="mb-1 flex items-baseline gap-3">
          <div className="text-4xl font-extrabold tabular-nums">{currentItems}</div>
          <div className="text-xl opacity-70">/ {plasticThreshold} items</div>
        </div>
        <div className={`mb-4 text-sm font-semibold ${isAbove ? "text-signal-bad" : "text-signal-good"}`}>
          {isAbove
            ? `🚨 ${currentItems - plasticThreshold} items over your limit`
            : `✓ ${plasticThreshold - currentItems} items remaining in budget`}
        </div>
        <div className="mb-3 h-4 overflow-hidden rounded-full bg-foreground/10">
          <div
            className={`h-full rounded-full transition-all duration-700 ${isAbove ? "bg-signal-bad" : "bg-signal-good"}`}
            style={{ width: `${pct}%` }}
          />
        </div>
        <div className="flex justify-between text-xs opacity-50">
          <span>0</span>
          <span>Limit: {plasticThreshold} items/week</span>
        </div>
      </div>
    </SectionShell>
  );
}

function GlobalSection() {

  return (
    <SectionShell bg={BG.global} overlayClass="bg-gradient-to-b from-black/85 via-black/80 to-black/90">
      <h2 className="section-title">🌿 Compost Planning</h2>


      {/* Optimized Disposal Schedule */}
      {(() => {
        const sorted = [...dailyForecast].sort((a, b) => a.value - b.value);
        const best = sorted.slice(0, 2);
        const worst = sorted.slice(-2).reverse();
        const bestDays = best.map(d => d.day).join(" & ");
        return (
          <div className="card-brand-success mb-6">
            <div className="mb-4 flex items-center gap-3">
              <span className="text-3xl">📅</span>
              <div>
                <div className="stat-label">Optimized Disposal Schedule</div>
                <div className="text-xs opacity-60 mt-0.5">Based on next-week forecast — schedule pickups on lowest-waste days</div>
              </div>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <div className="mb-2 text-xs font-bold uppercase tracking-wider text-signal-good">Best Days to Dispose</div>
                <div className="space-y-2">
                  {best.map((d, i) => (
                    <div key={d.day} className="flex items-center justify-between rounded-lg border border-signal-good/30 bg-signal-good/10 px-3 py-2">
                      <div className="flex items-center gap-2">
                        <span className="text-lg">{i === 0 ? "🥇" : "🥈"}</span>
                        <span className="font-bold">{
                          { Mon: "Monday", Tue: "Tuesday", Wed: "Wednesday", Thu: "Thursday", Fri: "Friday", Sat: "Saturday", Sun: "Sunday" }[d.day] ?? d.day
                        }</span>
                      </div>
                      <span className="font-bold tabular-nums text-signal-good">{d.value} lbs</span>
                    </div>
                  ))}
                </div>
              </div>
              <div>
                <div className="mb-2 text-xs font-bold uppercase tracking-wider text-signal-bad">Avoid These Days</div>
                <div className="space-y-2">
                  {worst.map((d, i) => (
                    <div key={d.day} className="flex items-center justify-between rounded-lg border border-signal-bad/30 bg-signal-bad/10 px-3 py-2">
                      <div className="flex items-center gap-2">
                        <span className="text-lg">{i === 0 ? "🚨" : "⚠️"}</span>
                        <span className="font-bold">{
                          { Mon: "Monday", Tue: "Tuesday", Wed: "Wednesday", Thu: "Thursday", Fri: "Friday", Sat: "Saturday", Sun: "Sunday" }[d.day] ?? d.day
                        }</span>
                      </div>
                      <span className="font-bold tabular-nums text-signal-bad">{d.value} lbs</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
            <div className="mt-4 rounded-lg border border-signal-good/20 bg-signal-good/5 px-3 py-2 text-sm text-signal-good">
              💡 Schedule compost pickup on <strong>{bestDays}</strong> to minimize disposal cost
            </div>
          </div>
        );
      })()}

      {/* Daily Forecast Breakdown */}
      <div className="card-brand mb-6">
        <h3 className="mb-6 text-lg font-bold uppercase tracking-wide text-brand-tan">
          Locality Level Daily Forecast Breakdown
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
        <div className="mb-4 flex items-center gap-4">
          <div className="icon-tile h-14 w-14 border-signal-good/60 bg-signal-good/20">
            <Factory className="h-7 w-7 text-signal-good" />
          </div>
          <div className="flex-1">
            <h3 className="text-xl font-bold uppercase tracking-wide">Nearby Composting Facilities</h3>
            <div className="mt-1 flex items-center gap-3 text-sm">
              <span className="font-semibold text-signal-good">{mockInsight.nearest_facility_name}</span>
              <span className="opacity-60">·</span>
              <span className="flex items-center gap-1 opacity-70">
                <MapPin className="h-3 w-3" />
                {((mockInsight.nearest_facility_km ?? 2.4) * KM_TO_MI).toFixed(1)} mi
              </span>
            </div>
          </div>
        </div>
        <div className="overflow-hidden rounded-xl border border-signal-good/30">
          <iframe
            title="Composting Facilities Near You"
            src="https://maps.google.com/maps?q=composting+facility+near+San+Diego+CA+92101&output=embed"
            width="100%"
            height="300"
            style={{ border: 0 }}
            allowFullScreen
            loading="lazy"
            referrerPolicy="no-referrer-when-downgrade"
          />
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
          if (mockInsight.sustainability_score != null) mockInsight.sustainability_score = Number(mockInsight.sustainability_score);
          if (mockInsight.signal_1 != null) mockInsight.signal_1 = Number(mockInsight.signal_1);
          if (mockInsight.signal_2 != null) mockInsight.signal_2 = Number(mockInsight.signal_2);
          if (mockInsight.signal_3 != null) mockInsight.signal_3 = Number(mockInsight.signal_3);
          if (mockInsight.signal_4 != null) mockInsight.signal_4 = Number(mockInsight.signal_4);
          if (mockInsight.signal_5 != null) mockInsight.signal_5 = Number(mockInsight.signal_5);
          if (mockInsight.co2_avoided != null) mockInsight.co2_avoided = Number(mockInsight.co2_avoided);
          if (mockInsight.nearest_facility_km != null) mockInsight.nearest_facility_km = Number(mockInsight.nearest_facility_km);
          if (!mockInsight.nearest_facility_name) mockInsight.nearest_facility_name = "Mission Valley Organics";
          // Push weekly totals into mockScan (coerced to number)
          if (insight.weekly_food_kg != null) mockScan.weekly_food_kg = Number(insight.weekly_food_kg);
          if (insight.weekly_dollar_waste != null) mockScan.weekly_dollar_waste = Number(insight.weekly_dollar_waste);
          if (insight.weekly_plastic_count != null) mockScan.weekly_plastic_count = Number(insight.weekly_plastic_count);
          if (insight.forecast_food_kg != null) mockScan.forecast_food_kg = Number(insight.forecast_food_kg);
          if (insight.forecast_dollar_waste != null) mockScan.forecast_next_week = Number(insight.forecast_dollar_waste);
        }
        if (locality) {
          Object.assign(mockLocality, locality);
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
