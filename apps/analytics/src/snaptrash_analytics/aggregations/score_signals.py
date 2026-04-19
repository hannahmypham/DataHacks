"""SnapTrash sustainability score (Person B spec) — pure functions only.

Maps scan table field names to spec names:
  total_food_kg      → pass restaurant / ZIP food kg (e.g. per-scan AVG or SUM as you choose)
  total_plastic_kg   → same for plastic
  harmful_count      → harmful_plastic_count
  total_plastic_count → plastic_count

All functions are side-effect free and safe to call from SQL-backed jobs or tests.
"""
from __future__ import annotations

import math
from typing import Literal


def signal1_food_vs_zip(restaurant_food_kg: float, zip_avg_food_kg: float) -> float:
    """Food waste vs ZIP average (20%). At or below ZIP avg = 100; each 1% above loses 1 point."""
    z = float(zip_avg_food_kg)
    r = float(restaurant_food_kg)
    if z <= 0.0:
        return 100.0
    pct_above = (r - z) / z * 100.0
    return max(0.0, min(100.0, 100.0 - pct_above))


def signal2_banned_harmful_plastics(ban_flag_count: int, harmful_count: int) -> float:
    """Banned + harmful plastics (20%).

    Penalty weights:
    - 25 pts per banned item  — higher weight because banned items are a legal violation (CA SB-54)
    - 10 pts per harmful item — non-banned but releases carcinogens (IARC Group 2B / WHO 2021)
    Score floor = 0.
    """
    plastic_penalty = (int(ban_flag_count) * 25) + (int(harmful_count) * 10)
    return max(0.0, 100.0 - plastic_penalty)


def signal3_recyclability_rate(recyclable_count: int, total_plastic_count: int) -> float:
    """Recyclability rate (20%). HDPE/PET/PP counted upstream in recyclable_count."""
    t = int(total_plastic_count)
    if t <= 0:
        return 100.0
    return max(0.0, min(100.0, (int(recyclable_count) / t) * 100.0))


def signal4_plastic_vs_zip(restaurant_plastic_kg: float, zip_avg_plastic_kg: float) -> float:
    """Plastic weight vs ZIP average (20%). Same 1% rule as signal 1."""
    z = float(zip_avg_plastic_kg)
    r = float(restaurant_plastic_kg)
    if z <= 0.0:
        return 100.0
    pct_above = (r - z) / z * 100.0
    return max(0.0, min(100.0, 100.0 - pct_above))


def signal5_week_over_week_reduction(
    this_week_avg: float | None,
    last_week_avg: float | None,
) -> float:
    """WoW total weight (food + plastic) trend (20%).

    Cold-start (no prior week) → 50.0 (neutral; neither rewarded nor penalised).
    Scoring curve:
    - ≥20% reduction → 100 (full marks; 20% is the EPA voluntary goal for commercial food waste)
    - 0–20% reduction → 50–100 linear (slope: 2.5 pts per 1% reduction)
    - 0% change → 50 (neutral)
    - Increase → 0–50 linear (penalised symmetrically; floor = 0)
    """
    if last_week_avg is None:
        return 50.0
    last = float(last_week_avg)
    this = float(this_week_avg if this_week_avg is not None else 0.0)
    if math.isnan(last) or math.isnan(this):
        return 50.0
    if last <= 0.0:
        return 50.0
    pct_reduction = (last - this) / last * 100.0
    if pct_reduction >= 20.0:   # EPA Sustainable Materials Management 20% goal
        return 100.0
    if pct_reduction > 0.0:
        return 50.0 + (pct_reduction * 2.5)
    if pct_reduction == 0.0:
        return 50.0
    return max(0.0, 50.0 + (pct_reduction * 2.5))


def sustainability_score(
    signal1: float,
    signal2: float,
    signal3: float,
    signal4: float,
    signal5: float,
) -> float:
    """Equal-weight blend of the five signals, mapped to 1–4 scale."""
    raw = (signal1 + signal2 + signal3 + signal4 + signal5) * 0.20
    score_1_4 = 1.0 + (raw / 100.0) * 3.0
    return max(1.0, min(4.0, round(score_1_4, 1)))


TierKey = Literal[
    "thriving_forest",
    "full_tree",
    "growing_plant",
    "small_sprout",
    "seed",
    "bare_root",
]


def tier_for_score(score: float) -> tuple[str, str, TierKey]:
    """Tier display name, emoji, asset key (for /assets/badges/{tier_key}.png). Score is 1–4."""
    if score >= 3.7:
        return ("Thriving Forest", "🌳", "thriving_forest")
    if score >= 3.4:
        return ("Full Tree", "🌲", "full_tree")
    if score >= 3.1:
        return ("Growing Plant", "🌿", "growing_plant")
    if score >= 2.8:
        return ("Small Sprout", "🌱", "small_sprout")
    if score >= 2.5:
        return ("Seed", "🌰", "seed")
    return ("Bare Root", "🪨", "bare_root")


def feedback_message(
    signal1: float,
    signal2: float,
    signal3: float,
    signal4: float,
    signal5: float,
) -> str:
    """One-line tip from the weakest signal (private dashboard)."""
    worst = min(
        [
            (signal1, "Reduce food waste volume"),
            (signal2, "Switch to non-banned plastics"),
            (signal3, "Use more recyclable packaging"),
            (signal4, "Reduce total plastic weight"),
            (signal5, "Keep improving week over week"),
        ],
        key=lambda x: x[0],
    )
    return worst[1]


def compute_all_signals_and_score(
    *,
    restaurant_food_kg: float,
    zip_avg_food_kg: float,
    ban_flag_count: int,
    harmful_count: int,
    recyclable_count: int,
    total_plastic_count: int,
    restaurant_plastic_kg: float,
    zip_avg_plastic_kg: float,
    this_week_avg_scan_weight: float | None,
    last_week_avg_scan_weight: float | None,
) -> tuple[float, float, float, float, float, float]:
    """Convenience: raw inputs → (s1, s2, s3, s4, s5, sustainability_score)."""
    s1 = signal1_food_vs_zip(restaurant_food_kg, zip_avg_food_kg)
    s2 = signal2_banned_harmful_plastics(ban_flag_count, harmful_count)
    s3 = signal3_recyclability_rate(recyclable_count, total_plastic_count)
    s4 = signal4_plastic_vs_zip(restaurant_plastic_kg, zip_avg_plastic_kg)
    s5 = signal5_week_over_week_reduction(this_week_avg_scan_weight, last_week_avg_scan_weight)
    total = sustainability_score(s1, s2, s3, s4, s5)
    return (s1, s2, s3, s4, s5, total)
