import { useEffect, useMemo, useRef, useState } from "react";
import type { Insight, LocalityAgg } from "./lib/api";
import { getInsights, getLocality, getWeeklySeries } from "./lib/api";
import { cn } from "./lib/cn";

const RESTAURANT_ID = "test-restaurant-001";
const ZIP = "92101";
const NEIGHBORHOOD = "Downtown San Diego";

// ── Static mock insights (mirrors schemas from lib/api.ts) ────────────────────
const MOCK_INSIGHTS: Insight = {
  restaurant_id: RESTAURANT_ID,
  computed_at: new Date().toISOString(),
  weekly_dollar_waste: 245.8,
  weekly_food_kg: 87.4,
  weekly_plastic_count: 142,
  forecast_dollar_waste: 312.5,
  forecast_food_kg: 112,
  forecast_plastic_count: 168,
  locality_percentile: 0.78,
  better_than_count: 37,
  zip_restaurant_count: 47,
  sustainability_score: 84,
  badge_tier: "Gold",
  score_feedback_message:
    "Better than 78% of restaurants in your ZIP. Keep reducing single-use plastics!",
  top_waste_category: "Plastic",
  peak_waste_day: "Wednesday",
  peak_waste_day_kg: 18.2,
  recommendation:
    "Focus staff training on portion control Wednesdays. Compost aggressively to hit 2-day shelf target.",
  co2_avoided: 4.2,
  shelf_life_min_days: 1,
  at_risk_kg_24h: 4.2,
  nearest_facility_name: "BioCycle Facility #3",
  nearest_facility_km: 2.1,
  harmful_plastic_count: 23,
  ban_flag_count: 7,
  enzyme_alert: true,
};

const MOCK_LOCALITY: LocalityAgg = {
  zip: ZIP,
  neighborhood: NEIGHBORHOOD,
  total_pet_kg: 312.4,
  total_ps_count: 88,
  harmful_count: 23,
  active_restaurants: 47,
  enzyme_alert: true,
};

const WEEKLY_SERIES = [
  { day: "M", actual: 12.4, forecast: 15.1 },
  { day: "T", actual: 9.8, forecast: 11.2 },
  { day: "W", actual: 18.2, forecast: 22.5 },
  { day: "T", actual: 14.1, forecast: 13.8 },
  { day: "F", actual: 16.7, forecast: 18.9 },
  { day: "S", actual: 11.3, forecast: 10.5 },
  { day: "S", actual: 8.9, forecast: 14.2 },
];

// ── Counter ───────────────────────────────────────────────────────────────────
interface CounterProps {
  target: number;
  suffix?: string;
  decimals?: number;
  active: boolean;
  className?: string;
  durationMs?: number;
}

function Counter({
  target,
  suffix = "",
  decimals = 0,
  active,
  className,
  durationMs = 900,
}: CounterProps) {
  const [value, setValue] = useState(0);
  const started = useRef(false);

  useEffect(() => {
    if (!active || started.current) return;
    started.current = true;
    const start = performance.now();
    const ease = (t: number) => 1 - Math.pow(1 - t, 3);
    const step = (now: number) => {
      const p = Math.min((now - start) / durationMs, 1);
      setValue(ease(p) * target);
      if (p < 1) requestAnimationFrame(step);
      else setValue(target);
    };
    requestAnimationFrame(step);
  }, [active, target, durationMs]);

  const formatted =
    decimals > 0
      ? value.toFixed(decimals)
      : Math.floor(value).toLocaleString();

  return (
    <span className={cn("tabular-nums", className)}>
      {formatted}
      {suffix}
    </span>
  );
}

// ── Catmull-Rom spline path builder ───────────────────────────────────────────
function catmullPath(pts: [number, number][]) {
  if (!pts.length) return "";
  let d = `M ${pts[0][0]},${pts[0][1]}`;
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[Math.max(i - 1, 0)];
    const p1 = pts[i];
    const p2 = pts[i + 1];
    const p3 = pts[Math.min(i + 2, pts.length - 1)];
    const cx1 = p1[0] + (p2[0] - p0[0]) / 6;
    const cy1 = p1[1] + (p2[1] - p0[1]) / 6;
    const cx2 = p2[0] - (p3[0] - p1[0]) / 6;
    const cy2 = p2[1] - (p3[1] - p1[1]) / 6;
    d += ` C ${cx1},${cy1} ${cx2},${cy2} ${p2[0]},${p2[1]}`;
  }
  return d;
}

// ── Sparkline (actual vs forecast) ────────────────────────────────────────────
interface SparkProps {
  series: { day: string; actual: number; forecast: number }[];
  active: boolean;
}

function Sparkline({ series, active }: SparkProps) {
  const { actualPath, forecastPath, areaPath, dots, labels } = useMemo(() => {
    const xs = series.map((_, i) => 22 + ((238 - 22) / (series.length - 1)) * i);
    const vMin = Math.min(...series.flatMap((s) => [s.actual, s.forecast]));
    const vMax = Math.max(...series.flatMap((s) => [s.actual, s.forecast]));
    const yMin = 4;
    const yMax = 46;
    const toY = (v: number) =>
      yMax - ((v - vMin) / Math.max(vMax - vMin, 0.0001)) * (yMax - yMin);

    const actualPts: [number, number][] = xs.map((x, i) => [
      x,
      toY(series[i].actual),
    ]);
    const forecastPts: [number, number][] = xs.map((x, i) => [
      x,
      toY(series[i].forecast),
    ]);

    const a = catmullPath(actualPts);
    const f = catmullPath(forecastPts);
    const area = `${a} L ${actualPts[actualPts.length - 1][0]},50 L ${actualPts[0][0]},50 Z`;

    return {
      actualPath: a,
      forecastPath: f,
      areaPath: area,
      dots: actualPts,
      labels: xs.map((x, i) => ({ x, label: series[i].day })),
    };
  }, [series]);

  return (
    <div className="sw-spark">
      <svg viewBox="0 0 260 60" preserveAspectRatio="none">
        <defs>
          <linearGradient id="sw-spark-grad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#90caf9" stopOpacity="0.35" />
            <stop offset="100%" stopColor="#90caf9" stopOpacity="0" />
          </linearGradient>
        </defs>
        <line className="sw-axis" x1="22" y1="4" x2="22" y2="50" />
        <line className="sw-axis" x1="22" y1="50" x2="238" y2="50" />
        {labels.map((l, i) => (
          <text
            key={i}
            x={l.x}
            y={58}
            fontSize="8"
            fill="rgba(255,255,255,0.35)"
            textAnchor="middle"
            fontFamily="DM Mono, monospace"
          >
            {l.label}
          </text>
        ))}
        {active && (
          <>
            <path className="sw-area" d={areaPath} />
            <path className="sw-line-alt" d={forecastPath} />
            <path className="sw-line" d={actualPath} />
            {dots.map(([x, y], i) => {
              const last = i === dots.length - 1;
              return (
                <circle
                  key={i}
                  cx={x}
                  cy={y}
                  r={last ? 4 : 2.5}
                  className={last ? "sw-dot-active" : "sw-dot"}
                />
              );
            })}
          </>
        )}
      </svg>
      <div className="flex justify-center gap-4 mt-2 text-[10px] text-white/60">
        <span className="inline-flex items-center gap-1.5">
          <span
            style={{
              width: 12,
              height: 2,
              background: "#90caf9",
              display: "inline-block",
            }}
          />
          Actual
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span
            style={{
              width: 12,
              height: 2,
              background: "#bbdefb",
              display: "inline-block",
              borderTop: "1px dashed #bbdefb",
            }}
          />
          Forecast
        </span>
      </div>
    </div>
  );
}

// ── Card ──────────────────────────────────────────────────────────────────────
interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  active: boolean;
  delay?: number;
  tall?: boolean;
  wide?: boolean;
}

function Card({
  active,
  delay = 0,
  tall,
  wide,
  className,
  children,
  ...rest
}: CardProps) {
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    if (!active) return;
    const t = setTimeout(() => setVisible(true), delay);
    return () => clearTimeout(t);
  }, [active, delay]);
  return (
    <div
      {...rest}
      className={cn(
        "sw-card",
        tall && "sw-tall",
        wide && "sw-wide",
        visible && "sw-visible",
        className,
      )}
    >
      {children}
    </div>
  );
}

// ── SVGs: Logo, Trash Cans, Cat, Decorations ──────────────────────────────────
const LogoSVG = () => (
  <svg width="34" height="38" viewBox="0 0 40 44" fill="none">
    <rect
      x="6"
      y="16"
      width="28"
      height="26"
      rx="2"
      fill="rgba(255,255,255,0.9)"
    />
    <rect
      x="4"
      y="10"
      width="32"
      height="7"
      rx="1.5"
      fill="rgba(255,255,255,0.9)"
    />
    <rect
      x="13"
      y="4"
      width="14"
      height="8"
      rx="1.5"
      fill="rgba(255,255,255,0.9)"
    />
    <rect x="13" y="20" width="2" height="18" rx="1" fill="rgba(0,20,80,0.2)" />
    <rect x="25" y="20" width="2" height="18" rx="1" fill="rgba(0,20,80,0.2)" />
    <circle cx="20" cy="7" r="5" fill="rgba(255,255,255,0.9)" />
    <polygon points="15,3 12,0 17,4" fill="rgba(255,255,255,0.9)" />
    <polygon points="25,3 28,0 23,4" fill="rgba(255,255,255,0.9)" />
    <path
      d="M31 8 Q36 5 34 2"
      stroke="rgba(255,255,255,0.9)"
      strokeWidth="2"
      fill="none"
      strokeLinecap="round"
    />
  </svg>
);

const MainCanSVG = () => (
  <svg width="100" height="110" viewBox="0 0 100 110" fill="none">
    <rect
      x="10"
      y="15"
      width="80"
      height="12"
      rx="3.5"
      fill="rgba(40,70,160,0.7)"
    />
    <rect
      x="35"
      y="5"
      width="30"
      height="12"
      rx="3.5"
      fill="rgba(40,70,160,0.7)"
    />
    <rect
      x="14"
      y="27"
      width="72"
      height="80"
      rx="5"
      fill="rgba(30,60,150,0.6)"
    />
    <rect
      x="34"
      y="38"
      width="5"
      height="58"
      rx="2.5"
      fill="rgba(0,0,60,0.18)"
    />
    <rect
      x="61"
      y="38"
      width="5"
      height="58"
      rx="2.5"
      fill="rgba(0,0,60,0.18)"
    />
  </svg>
);

const TomSVG = () => (
  <svg width="52" height="58" viewBox="0 0 54 60" fill="none">
    <ellipse cx="27" cy="38" rx="14" ry="16" fill="rgba(255,248,230,0.95)" />
    <circle cx="27" cy="20" r="14" fill="rgba(255,248,230,0.95)" />
    <polygon points="13,10 8,0 20,8" fill="rgba(255,248,230,0.95)" />
    <polygon points="41,10 46,0 34,8" fill="rgba(255,248,230,0.95)" />
    <path
      d="M21 18 Q23 15 25 18"
      stroke="#2c3e70"
      strokeWidth="1.5"
      strokeLinecap="round"
      fill="none"
    />
    <path
      d="M29 18 Q31 15 33 18"
      stroke="#2c3e70"
      strokeWidth="1.5"
      strokeLinecap="round"
      fill="none"
    />
    <ellipse cx="27" cy="22" rx="2" ry="1.5" fill="#f8bbd0" />
    <path
      d="M24 24 Q27 27 30 24"
      stroke="rgba(100,100,150,0.5)"
      strokeWidth="1"
      fill="none"
      strokeLinecap="round"
    />
    <path
      d="M40 50 Q56 44 52 34 Q50 28 44 32"
      stroke="rgba(255,248,230,0.95)"
      strokeWidth="5"
      fill="none"
      strokeLinecap="round"
    />
    <ellipse cx="17" cy="52" rx="5" ry="7" fill="rgba(255,248,230,0.95)" />
    <ellipse cx="37" cy="52" rx="5" ry="7" fill="rgba(255,248,230,0.95)" />
  </svg>
);

const SideCansSVG = () => (
  <div className="sw-deco sw-deco-active">
    <svg
      width="82"
      height="108"
      viewBox="0 0 82 108"
      fill="none"
      style={{
        position: "absolute",
        bottom: 0,
        left: "50%",
        marginLeft: -188,
      }}
    >
      <rect x="11" y="28" width="60" height="76" rx="4" fill="rgba(70,95,155,0.65)" />
      <rect x="6" y="17" width="70" height="13" rx="3" fill="rgba(90,115,175,0.65)" />
      <rect x="24" y="6" width="34" height="13" rx="3" fill="rgba(90,115,175,0.65)" />
      <rect x="24" y="35" width="4" height="56" rx="2" fill="rgba(0,0,60,0.18)" />
      <rect x="54" y="35" width="4" height="56" rx="2" fill="rgba(0,0,60,0.18)" />
      <circle cx="41" cy="14" r="9" fill="#ef9a9a" opacity="0.9" />
      <path d="M41 5 Q45 1 47 5" stroke="#66bb6a" strokeWidth="2" fill="none" />
      <circle cx="28" cy="20" r="7" fill="#fff176" opacity="0.85" />
    </svg>
    <svg
      width="78"
      height="100"
      viewBox="0 0 78 100"
      fill="none"
      style={{
        position: "absolute",
        bottom: 0,
        left: "50%",
        marginLeft: 110,
      }}
    >
      <rect x="10" y="24" width="58" height="74" rx="4" fill="rgba(70,95,155,0.65)" />
      <rect x="5" y="14" width="68" height="12" rx="3" fill="rgba(90,115,175,0.65)" />
      <rect x="22" y="4" width="34" height="12" rx="3" fill="rgba(90,115,175,0.65)" />
      <rect x="22" y="32" width="4" height="54" rx="2" fill="rgba(0,0,60,0.18)" />
      <rect x="52" y="32" width="4" height="54" rx="2" fill="rgba(0,0,60,0.18)" />
      <rect
        x="32"
        y="4"
        width="16"
        height="26"
        rx="8"
        fill="#e3f2fd"
        opacity="0.85"
        stroke="rgba(100,150,255,0.5)"
        strokeWidth="1"
      />
      <rect x="37" y="2" width="6" height="5" rx="2" fill="#bbdefb" opacity="0.85" />
    </svg>
  </div>
);

const PlasticDecoSVG = ({ active }: { active: boolean }) => (
  <div className={cn("sw-deco", active && "sw-deco-active")}>
    <svg
      width="260"
      height="100"
      viewBox="0 0 260 100"
      fill="none"
      style={{ position: "absolute", bottom: 0, left: 20 }}
    >
      <rect
        x="10"
        y="28"
        width="22"
        height="52"
        rx="11"
        fill="#e3f2fd"
        opacity="0.85"
        stroke="rgba(100,180,255,0.5)"
        strokeWidth="1"
      />
      <rect x="15" y="24" width="12" height="8" rx="3" fill="#bbdefb" opacity="0.85" />
      <g transform="rotate(-35,80,80)">
        <rect
          x="55"
          y="60"
          width="20"
          height="48"
          rx="10"
          fill="#e1f5fe"
          opacity="0.8"
          stroke="rgba(100,180,255,0.5)"
          strokeWidth="1"
        />
        <rect x="60" y="56" width="10" height="7" rx="2" fill="#b3e5fc" opacity="0.8" />
      </g>
      <rect
        x="120"
        y="35"
        width="18"
        height="44"
        rx="9"
        fill="#f3e5f5"
        opacity="0.8"
        stroke="rgba(180,100,255,0.4)"
        strokeWidth="1"
      />
      <rect x="124" y="31" width="10" height="7" rx="2" fill="#e1bee7" opacity="0.8" />
      <path
        d="M170 90 Q175 60 190 50 Q205 60 200 90 Z"
        fill="rgba(255,255,255,0.2)"
        stroke="rgba(200,220,255,0.5)"
        strokeWidth="1.5"
      />
      <line
        x1="182"
        y1="50"
        x2="185"
        y2="40"
        stroke="rgba(200,220,255,0.5)"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
      <line
        x1="193"
        y1="50"
        x2="190"
        y2="40"
        stroke="rgba(200,220,255,0.5)"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
    </svg>
    <svg
      width="120"
      height="80"
      viewBox="0 0 120 80"
      fill="none"
      style={{ position: "absolute", bottom: 0, right: 30 }}
    >
      <rect
        x="20"
        y="20"
        width="20"
        height="48"
        rx="10"
        fill="#e3f2fd"
        opacity="0.8"
        stroke="rgba(100,180,255,0.5)"
        strokeWidth="1"
      />
      <rect x="25" y="16" width="10" height="7" rx="2" fill="#bbdefb" opacity="0.8" />
      <rect
        x="70"
        y="30"
        width="16"
        height="38"
        rx="8"
        fill="#e8f5e9"
        opacity="0.75"
        stroke="rgba(100,200,150,0.4)"
        strokeWidth="1"
      />
      <rect x="74" y="27" width="8" height="6" rx="2" fill="#c8e6c9" opacity="0.8" />
    </svg>
  </div>
);

const FoodDecoSVG = ({ active }: { active: boolean }) => (
  <div className={cn("sw-deco", active && "sw-deco-active")}>
    <svg
      width="300"
      height="110"
      viewBox="0 0 300 110"
      fill="none"
      style={{ position: "absolute", bottom: 0, left: 10 }}
    >
      <circle cx="40" cy="70" r="24" fill="#ef9a9a" opacity="0.9" />
      <path
        d="M40 46 Q45 38 48 42"
        stroke="#66bb6a"
        strokeWidth="2.5"
        fill="none"
        strokeLinecap="round"
      />
      <circle cx="58" cy="58" r="10" fill="rgba(144,202,249,0.6)" />
      <path d="M110 40 L100 90" stroke="#ff8a65" strokeWidth="10" strokeLinecap="round" />
      <path
        d="M110 40 L105 28 M110 40 L115 26 M110 40 L120 32"
        stroke="#66bb6a"
        strokeWidth="2"
        strokeLinecap="round"
      />
      <path
        d="M160 80 Q175 50 195 55 Q205 58 190 80 Z"
        fill="#fff176"
        opacity="0.9"
        stroke="#f9a825"
        strokeWidth="1"
      />
      <ellipse cx="240" cy="85" rx="28" ry="14" fill="#a5d6a7" opacity="0.85" />
      <ellipse cx="245" cy="78" rx="18" ry="10" fill="#81c784" opacity="0.85" />
    </svg>
    <svg
      width="140"
      height="110"
      viewBox="0 0 140 110"
      fill="none"
      style={{ position: "absolute", bottom: 0, right: 20 }}
    >
      <ellipse cx="60" cy="55" rx="28" ry="22" fill="#ffcc80" opacity="0.9" />
      <ellipse cx="60" cy="52" rx="24" ry="18" fill="#ffa726" opacity="0.85" />
      <rect x="57" y="70" width="6" height="32" rx="3" fill="#d7ccc8" opacity="0.9" />
      <ellipse cx="60" cy="100" rx="10" ry="5" fill="#bcaaa4" opacity="0.9" />
      <circle cx="110" cy="72" r="18" fill="#ce93d8" opacity="0.85" />
      <path
        d="M110 54 Q115 46 118 50"
        stroke="#66bb6a"
        strokeWidth="2"
        fill="none"
        strokeLinecap="round"
      />
    </svg>
  </div>
);

// ── Main ──────────────────────────────────────────────────────────────────────
export default function App() {
  const [insights, setInsights] = useState<Insight>(MOCK_INSIGHTS);
  const [locality, setLocality] = useState<LocalityAgg>(MOCK_LOCALITY);
  const [weeklySeries, setWeeklySeries] = useState(WEEKLY_SERIES);

  // Fetch real data; silently fall back to mock on error
  useEffect(() => {
    getInsights(RESTAURANT_ID)
      .then((data) => setInsights(data))
      .catch((err) => console.warn("[SnapWaste] insights unavailable, using mock:", err));

    getLocality(ZIP)
      .then((data) => setLocality(data))
      .catch((err) => console.warn("[SnapWaste] locality unavailable, using mock:", err));

    // Build weekly sparkline: actuals from scans, forecast derived from Prophet ratio
    getWeeklySeries(RESTAURANT_ID)
      .then((days) => {
        if (!days.length) return;
        // Will be refined once insights loaded — use ratio: forecast / actual total
        setWeeklySeries(
          days.map((d) => ({ day: d.day, actual: d.actual, forecast: d.actual }))
        );
        // Once insights also loads, recompute forecast column via ratio
        getInsights(RESTAURANT_ID).then((ins) => {
          const actualTotal = days.reduce((s, d) => s + d.actual, 0);
          const ratio = actualTotal > 0 ? (ins.forecast_food_kg ?? actualTotal) / actualTotal : 1;
          setWeeklySeries(
            days.map((d) => ({
              day: d.day,
              actual: d.actual,
              forecast: parseFloat((d.actual * ratio).toFixed(2)),
            }))
          );
        }).catch(() => {/* keep series without forecast scaling */});
      })
      .catch((err) => console.warn("[SnapWaste] weekly-series unavailable, using mock:", err));
  }, []);

  const scrollRef = useRef<HTMLDivElement | null>(null);
  const [activeScreen, setActiveScreen] = useState(1);

  useEffect(() => {
    const wrap = scrollRef.current;
    if (!wrap) return;
    const saved = localStorage.getItem("sw-screen");
    if (saved) {
      wrap.scrollTo({ top: +saved * window.innerHeight, behavior: "instant" });
    }
    const onScroll = () => {
      const s = Math.round(wrap.scrollTop / window.innerHeight);
      localStorage.setItem("sw-screen", String(s));
      setActiveScreen(s + 1);
    };
    wrap.addEventListener("scroll", onScroll, { passive: true });
    return () => wrap.removeEventListener("scroll", onScroll);
  }, []);

  const scrollTo = (idx: number) => {
    scrollRef.current?.scrollTo({
      top: idx * window.innerHeight,
      behavior: "smooth",
    });
  };

  // Data derivations from Insight schema
  const score = insights.sustainability_score ?? 84;
  const badge = insights.badge_tier ?? "Gold";
  const dollars = Math.round(insights.weekly_dollar_waste);
  const dollarsForecast = Math.round(insights.forecast_dollar_waste ?? 0);
  const percentilePct = Math.round(insights.locality_percentile * 100);
  const betterThan = insights.better_than_count ?? 37;
  const zipCount = insights.zip_restaurant_count ?? 47;
  const peakDay = insights.peak_waste_day ?? "Wednesday";
  const peakKg = insights.peak_waste_day_kg ?? 18.2;
  const nearestName = insights.nearest_facility_name ?? "BioCycle Facility #3";
  const nearestKm = insights.nearest_facility_km ?? 2.1;

  const plasticCount = insights.weekly_plastic_count ?? 0;
  const plasticForecast = insights.forecast_plastic_count ?? 0;
  const harmful = insights.harmful_plastic_count ?? 0;
  const banFlags = insights.ban_flag_count ?? 0;
  const enzymeAlert = locality.enzyme_alert ?? false;
  const localActive = locality.active_restaurants;

  const foodKg = insights.weekly_food_kg ?? 0;
  const foodLbs = Math.round(foodKg * 2.20462);
  const foodForecast = Math.round(insights.forecast_food_kg ?? 0);
  const shelfDays = insights.shelf_life_min_days ?? 1;
  const atRisk = insights.at_risk_kg_24h ?? 4.2;
  const feedback = insights.score_feedback_message ?? "";

  // Cards become active once their screen is in view (threshold-based reveal)
  const onScreen2 = activeScreen === 2;
  const onScreen3 = activeScreen === 3;
  const onScreen4 = activeScreen === 4;

  return (
    <>
      {/* Sky */}
      <div className="sw-sky">
        <div className="sw-sun" />
        <div className="sw-cloud" style={{ top: "14%", left: "8%", width: 120, height: 28 }} />
        <div className="sw-cloud" style={{ top: "14%", left: "9.5%", width: 80, height: 40 }} />
        <div className="sw-cloud" style={{ top: "22%", left: "28%", width: 160, height: 30 }} />
        <div className="sw-cloud" style={{ top: "22%", left: "30%", width: 100, height: 44 }} />
        <div
          className="sw-cloud"
          style={{ top: "10%", left: "55%", width: 90, height: 22, opacity: 0.5 }}
        />
      </div>

      {/* Scene */}
      <div className="sw-scene">
        <SideCansSVG />
        <PlasticDecoSVG active={onScreen3} />
        <FoodDecoSVG active={onScreen4} />
        <div className="sw-main-can">
          <MainCanSVG />
        </div>
      </div>

      {/* Tom */}
      <div className="sw-tom">
        <TomSVG />
      </div>

      {/* Header */}
      <div className="sw-header">
        <LogoSVG />
        <span className="sw-wordmark">SnapWaste</span>
      </div>

      {/* Dot nav */}
      <nav className="sw-dot-nav">
        {[0, 1, 2, 3].map((i) => (
          <button
            key={i}
            className={cn("sw-dot-btn", activeScreen === i + 1 && "sw-active")}
            onClick={() => scrollTo(i)}
            aria-label={`Screen ${i + 1}`}
          />
        ))}
      </nav>

      {/* Scroll */}
      <div ref={scrollRef} className="sw-scroll">
        {/* S1 Hero */}
        <section className="sw-section">
          <div className="sw-hero-title">SnapWaste</div>
          <div className="sw-hero-sub">
            Restaurant Waste Intelligence
          </div>
          <div className="sw-scroll-hint">
            <span>Scroll to explore</span>
            <div className="sw-scroll-arrow" />
          </div>
        </section>

        {/* S2 Overview */}
        <section className="sw-section">
          <div className="sw-screen-label">Overview · Sustainability & Forecast</div>

          <div className="sw-cards-row">
            {/* Sustainability score */}
            <Card active={onScreen2} delay={0}>
              <div className="sw-card-label">Sustainability Score</div>
              <div className="sw-card-value">
                <Counter target={score} active={onScreen2} />
              </div>
              <div className="sw-card-sub sw-c1">
                {badge} Tier
                <span className="sw-tag sw-ok">
                  <span className="sw-pulse-dot" /> live
                </span>
              </div>
            </Card>

            {/* Weekly $ waste */}
            <Card active={onScreen2} delay={100}>
              <div className="sw-card-label">Weekly $ Waste</div>
              <div className="sw-card-value">
                $<Counter target={dollars} active={onScreen2} />
              </div>
              <div className="sw-card-sub sw-c2">
                Forecast next week · ${dollarsForecast.toLocaleString()}
              </div>
            </Card>

            {/* ZIP percentile */}
            <Card active={onScreen2} delay={200}>
              <div className="sw-card-label">ZIP Percentile</div>
              <div className="sw-card-value" style={{ fontSize: 26 }}>
                Top <Counter target={percentilePct} suffix="%" active={onScreen2} />
              </div>
              <div className="sw-card-sub sw-c1">
                Better than {betterThan} of {zipCount} restaurants · {ZIP}
              </div>
              <div className="sw-progress">
                <div
                  className="sw-progress-fill"
                  style={{ width: onScreen2 ? `${percentilePct}%` : "0%" }}
                />
              </div>
            </Card>

            {/* Peak day */}
            <Card active={onScreen2} delay={300}>
              <div className="sw-card-label">Peak Waste Day</div>
              <div className="sw-card-value" style={{ fontSize: 24 }}>
                {peakDay}
              </div>
              <div className="sw-card-sub sw-c2">
                <Counter target={peakKg} decimals={1} suffix=" kg" active={onScreen2} /> this
                day · 28d rolling
              </div>
            </Card>

            {/* Nearest compost */}
            <Card active={onScreen2} delay={400}>
              <div className="sw-card-label">Nearest Compost</div>
              <a
                href={`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(nearestName)}`}
                target="_blank"
                rel="noopener noreferrer"
                style={{ textDecoration: "none", color: "inherit", display: "block" }}
              >
                <div className="sw-card-value" style={{ fontSize: 18 }}>
                  {nearestName} ↗
                </div>
              </a>
              <div className="sw-card-sub sw-c1">
                <Counter target={nearestKm} decimals={1} suffix=" km" active={onScreen2} />{" "}
                away · capacity open
              </div>
            </Card>

            {/* Forecast chart (tall) */}
            <Card active={onScreen2} delay={500} tall>
              <div className="sw-card-label">Weekly Forecast vs Actual</div>
              <div className="sw-card-value" style={{ fontSize: 18 }}>
                Prophet · Databricks
              </div>
              <div className="sw-card-sub sw-c2">Peak on {peakDay} · kg / day</div>
              <Sparkline series={weeklySeries} active={onScreen2} />
            </Card>
          </div>

          {/* Recommendation strip */}
          <div className={cn("sw-recommend", onScreen2 && "sw-visible")}>
            <em>Recommendation · </em>
            {insights.recommendation}
          </div>
        </section>

        {/* S3 Plastic */}
        <section className="sw-section">
          <div className="sw-screen-label">Plastic Waste Intelligence</div>
          <div className="sw-cards-row">
            <Card active={onScreen3} delay={0}>
              <div className="sw-card-label">Plastic Volume (items/week)</div>
              <div className="sw-card-value">
                <Counter target={plasticCount} active={onScreen3} />
              </div>
              <div className="sw-card-sub sw-c2">
                Forecast next week · {plasticForecast} items
              </div>
              <div className="sw-progress">
                <div
                  className="sw-progress-fill"
                  style={{
                    width: onScreen3
                      ? `${Math.min((plasticCount / 300) * 100, 95)}%`
                      : "0%",
                  }}
                />
              </div>
            </Card>

            <Card active={onScreen3} delay={100}>
              <div className="sw-card-label">Harmful / Banned Items</div>
              <div className="sw-card-value">
                <Counter target={harmful} active={onScreen3} />
              </div>
              <div className="sw-card-sub sw-c-warn">
                {banFlags} ban-flags · review suppliers
              </div>
            </Card>

            <Card active={onScreen3} delay={200}>
              <div className="sw-card-label">Enzyme Alert</div>
              <div className="sw-card-value" style={{ fontSize: 22 }}>
                {enzymeAlert ? "Active" : "Clear"}
                <span className={cn("sw-tag", enzymeAlert ? "sw-warn" : "sw-ok")}>
                  {enzymeAlert ? "attention" : "ok"}
                </span>
              </div>
              <div className="sw-card-sub sw-c4">
                ZIP {locality.zip} · {localActive} restaurants monitored
              </div>
            </Card>
          </div>
        </section>

        {/* S4 Food */}
        <section className="sw-section">
          <div className="sw-screen-label">Food Waste Analysis</div>
          <div className="sw-cards-row">
            <Card active={onScreen4} delay={0}>
              <div className="sw-card-label">Food Waste (week)</div>
              <div className="sw-card-value">
                <Counter target={foodLbs} suffix=" lb" active={onScreen4} />
              </div>
              <div className="sw-card-sub sw-c2">
                {foodKg.toFixed(1)} kg · forecast {foodForecast} kg next week
              </div>
            </Card>

            <Card active={onScreen4} delay={100}>
              <div className="sw-card-label">Compost Shelf Life</div>
              <div className="sw-card-value">
                <Counter target={shelfDays} suffix=" d" active={onScreen4} />
              </div>
              <div className="sw-card-sub sw-c-warn">
                <Counter target={atRisk} decimals={1} suffix=" kg" active={onScreen4} /> at
                risk · next 24h
              </div>
            </Card>

            <Card active={onScreen4} delay={200}>
              <div className="sw-card-label">Forecast Food (next week)</div>
              <div className="sw-card-value">
                <Counter target={foodForecast} suffix=" kg" active={onScreen4} />
              </div>
              <div className="sw-card-sub sw-c1">Prophet · Databricks · weekly</div>
            </Card>

            <Card active={onScreen4} delay={300} className="sw-feedback">
              <div className="sw-card-label">Score Feedback</div>
              <div className="sw-card-value" style={{ fontSize: 16, lineHeight: 1.35 }}>
                “{feedback}”
              </div>
              <div className="sw-card-sub sw-c2">
                Peak day · {peakDay} · plan prep accordingly
              </div>
            </Card>
          </div>
        </section>
      </div>
    </>
  );
}
