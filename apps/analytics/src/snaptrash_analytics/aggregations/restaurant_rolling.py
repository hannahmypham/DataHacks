"""7-day rolling stats per restaurant. Writes top_waste_category + recommendation to insights."""
from __future__ import annotations
from datetime import datetime, timezone
from snaptrash_common.databricks_client import execute, fetch_all
from snaptrash_common.tables import SCANS, INSIGHTS


SQL_ROLLING = f"""
SELECT
  restaurant_id,
  SUM(dollar_wastage) AS weekly_dollar_waste,
  SUM(food_kg) AS weekly_food_kg,
  SUM(ps_count) AS weekly_ps_count,
  SUM(pet_kg) AS weekly_pet_kg,
  AVG(CASE WHEN food_kg > 0 THEN compostable_kg/food_kg END) AS compost_yield_rate,
  SUM(co2_kg) AS weekly_co2,
  -- New sustainability fields
  SUM(ban_flag_count) AS total_ban_flag_count,
  SUM(recyclable_count) AS total_recyclable_count,
  SUM(total_plastic_kg) AS total_plastic_kg,
  SUM(plastic_count) AS total_plastic_count,
  SUM(harmful_plastic_count) AS total_harmful_count
FROM {SCANS}
WHERE timestamp >= now() - INTERVAL 7 DAYS
GROUP BY restaurant_id
"""


def recommendation(row: dict) -> str:
    if (row.get("weekly_ps_count") or 0) > 50:
        return "High PS foam usage — switch to PET clamshells."
    if (row.get("compost_yield_rate") or 0) < 0.5:
        return "Composting yield below 50%. Check contamination at source."
    if (row.get("weekly_dollar_waste") or 0) > 200:
        return "Weekly wastage > $200 — review portioning."
    return "On track. Maintain current practices."


def top_category(row: dict) -> str:
    if (row.get("weekly_ps_count") or 0) > 30:
        return "plastic"
    return "food"


def calculate_sustainability_score(row: dict) -> float:
    """Implements the 5-signal sustainability score from the spec.
    Full version would use additional ZIP avg (window over scans in same zip last 7d)
    and week-over-week history per restaurant. This uses aggregated fields as proxy.
    Extend with full SQL (CTE for zip_avgs + LAG for history) for production accuracy.
    See spec for exact GREATEST, CASE logic, and fallbacks (e.g. 50 if no history).
    """
    # Signal 2: Banned + Harmful Plastics (20%)
    ban_count = row.get("total_ban_flag_count", 0) or row.get("weekly_ps_count", 0)
    harmful_count = row.get("total_harmful_count", 0)
    plastic_penalty = (ban_count * 25) + (harmful_count * 10)
    signal2 = max(0, 100 - plastic_penalty)

    # Signal 3: Recyclability Rate (20%)
    recyclable = row.get("total_recyclable_count", 0)
    total_plastic = row.get("total_plastic_count", 0) or 1
    signal3 = min(100.0, (recyclable / total_plastic * 100) if total_plastic > 0 else 50.0)

    # Signals 1,4,5 approximated from aggregates (full impl requires per-zip/per-restaurant history queries)
    # Signal1/4: vs ZIP avg (use total_plastic_kg, food_kg vs peers)
    signal1 = 75.0  # placeholder for food vs ZIP
    signal4 = 80.0  # placeholder for plastic vs ZIP
    signal5 = 65.0  # placeholder for WoW reduction (neutral 50 if first week)

    sustainability_score = (
        signal1 * 0.20 +
        signal2 * 0.20 +
        signal3 * 0.20 +
        signal4 * 0.20 +
        signal5 * 0.20
    )
    return max(0.0, min(100.0, round(sustainability_score, 1)))


def get_badge_and_feedback(score: float) -> tuple[str | None, str]:
    """Grade mapping per spec."""
    if score >= 90:
        badge = "A+"
        feedback = "Sustainability Leader — exemplary performance across all signals!"
    elif score >= 80:
        badge = "A"
        feedback = "Excellent — strong waste reduction and responsible plastics use."
    elif score >= 70:
        badge = "B"
        feedback = "Above Average — good progress, target plastics next."
    elif score >= 60:
        badge = "C"
        feedback = "Average — room to improve food waste and banned plastics."
    elif score >= 50:
        badge = "D"
        feedback = "Below Average — focus on week-over-week reduction."
    else:
        badge = "F"
        feedback = "Needs Improvement — review banned plastics and ZIP benchmarks."
    return badge, f"Sustainability Score: {score}/100 — {feedback}"


def main():
    rows = fetch_all(SQL_ROLLING)
    now = datetime.now(timezone.utc).isoformat()
    for r in rows:
        score = calculate_sustainability_score(r)
        badge, feedback = get_badge_and_feedback(score)

        execute(
            f"""
            INSERT INTO {INSIGHTS} VALUES (
              :restaurant_id, :computed_at, :weekly_dollar_waste,
              0.0, 0.0, :top, :rec, :co2,
              :sustainability_score, :badge_tier, :score_feedback_message
            )
            """,
            {
                "restaurant_id": r["restaurant_id"],
                "computed_at": now,
                "weekly_dollar_waste": float(r.get("weekly_dollar_waste") or 0),
                "top": top_category(r),
                "rec": recommendation(r),
                "co2": float(r.get("weekly_co2") or 0),
                "sustainability_score": score,
                "badge_tier": badge,
                "score_feedback_message": feedback,
            },
        )
    print(f"✅ wrote {len(rows)} restaurant rolling rows with sustainability scores")


if __name__ == "__main__":
    main()
