"""
Sustainability score driver — wires pure spec functions in ``score_signals`` to
the scans_unified / insights pipeline.

Runs AFTER ``restaurant_rolling.py`` writes base insight rows. Computes the
five Person-B signals per restaurant (each 20%) and UPDATEs insights with:
  - sustainability_score (0–100)
  - signal_1..signal_5     (per-signal breakdown for dashboard)
  - badge_tier             (display name, e.g. "Thriving Forest")
  - tier_emoji, tier_key   (for /assets/badges/{tier_key}.png)
  - score_feedback_message (weakest-signal tip)
  - locality_percentile / better_than_count / zip_restaurant_count
  - nearest_facility_name / _km / _capacity_tons  (UI display only)
  - ca_network_capacity_tons

Signals (all 20% equal weight):
  1. food_vs_zip        — restaurant food kg vs ZIP average
  2. banned+harmful     — 25 pts/banned item, 10 pts/harmful item
  3. recyclability_rate — recyclable / total plastic count
  4. plastic_vs_zip     — restaurant plastic kg vs ZIP average
  5. WoW reduction      — (food_kg + plastic_kg) this week vs last week
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone

from snaptrash_common.databricks_client import execute, fetch_all
from snaptrash_common.geo import haversine
from snaptrash_common.tables import (
    SCANS_UNIFIED, INSIGHTS, GOLD_COMPOSTING, GOLD_CA_CAPACITY,
    GOLD_SD_COMMERCIAL, GOLD_SD_RESTAURANTS,
)

from .score_signals import (
    compute_all_signals_and_score,
    feedback_message,
    tier_for_score,
)

SD_LAT, SD_LNG = 32.7157, -117.1611

# EPA Food Recovery Hierarchy (2019): restaurants/food-service generate ~30%
# of the commercial food waste stream.
RESTAURANT_SHARE_OF_COMMERCIAL_FOOD = 0.30


# ---------------------------------------------------------------------------
# Haversine (facility distance — UI display only, not in score)
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# Reference data loaders
# ---------------------------------------------------------------------------

def _load_facilities() -> list[dict]:
    try:
        return fetch_all(
            f"SELECT facility_name, lat, lng, capacity_tons, dist_from_sd_center_km "
            f"FROM {GOLD_COMPOSTING} ORDER BY dist_from_sd_center_km ASC"
        )
    except Exception:
        return []


def _ca_network_capacity() -> int | None:
    try:
        rows = fetch_all(
            f"SELECT annual_capacity_tons FROM {GOLD_CA_CAPACITY} LIMIT 1"
        )
        if rows:
            return int(rows[0]["annual_capacity_tons"])
    except Exception:
        pass
    return None


def _sd_expected_food_kg_per_restaurant_per_week() -> float | None:
    try:
        rows = fetch_all(f"""
            SELECT SUM(sd_commercial_tons) AS food_tons
            FROM {GOLD_SD_COMMERCIAL}
            WHERE LOWER(material) = 'food'
        """)
        food_tons = float(rows[0]["food_tons"]) if rows and rows[0].get("food_tons") else 0.0
        rows2 = fetch_all(
            f"SELECT SUM(restaurant_count) AS n FROM {GOLD_SD_RESTAURANTS}"
        )
        n_rest = int(rows2[0]["n"]) if rows2 and rows2[0].get("n") else 0
        if food_tons <= 0 or n_rest <= 0:
            return None
        restaurant_food_tons = food_tons * RESTAURANT_SHARE_OF_COMMERCIAL_FOOD
        return (restaurant_food_tons * 907.185) / (n_rest * 52.0)
    except Exception:
        return None


_SD_ZIP_CENTROIDS: dict[str, tuple[float, float]] = {}


def _load_sd_zip_centroids() -> dict[str, tuple[float, float]]:
    global _SD_ZIP_CENTROIDS
    if _SD_ZIP_CENTROIDS:
        return _SD_ZIP_CENTROIDS
    try:
        import requests  # noqa: PLC0415
        url = ("https://opendata.arcgis.com/datasets/"
               "41c3a7bd375547069a78fce90153f39c_0.geojson")
        resp = requests.get(url, timeout=15)
        geojson = resp.json()
        for feat in geojson.get("features", []):
            zip5 = feat["properties"].get("ZCTA5CE20") or feat["properties"].get("zip")
            if not zip5:
                continue
            coords = feat["geometry"]["coordinates"][0]
            if isinstance(coords[0], list):
                coords = coords[0]
            lat = sum(c[1] for c in coords) / len(coords)
            lng = sum(c[0] for c in coords) / len(coords)
            _SD_ZIP_CENTROIDS[str(zip5)] = (lat, lng)
        print(f"  Loaded {len(_SD_ZIP_CENTROIDS)} SD ZIP centroids from GIS")
    except Exception as e:
        print(f"  Warning: could not load ZIP centroids ({e}). Using SD center.")
    return _SD_ZIP_CENTROIDS


def _nearest_facility(zip_lat: float, zip_lng: float,
                      facilities: list[dict]) -> tuple[str | None, float | None, int | None]:
    if not facilities:
        return None, None, None
    best = (None, float("inf"), None)
    for f in facilities:
        try:
            dist = haversine(zip_lat, zip_lng, float(f["lat"]), float(f["lng"]))
            if dist < best[1]:
                cap = f.get("capacity_tons")
                best = (f["facility_name"], dist, int(cap) if cap else None)
        except (TypeError, ValueError):
            continue
    if best[0] is None:
        return None, None, None
    return best[0], round(best[1], 2), best[2]


# ---------------------------------------------------------------------------
# Scan aggregate loaders
# ---------------------------------------------------------------------------

# Per-restaurant 7-day actuals (this week) — includes plastic-kg proxy.
# PET kg is measured; PS foam approximated at 0.02 kg/item; others negligible.
SQL_RESTAURANT_WEEK = f"""
SELECT
  restaurant_id,
  ANY_VALUE(zip)                                 AS zip,
  ANY_VALUE(neighborhood)                        AS neighborhood,
  SUM(food_kg)                                   AS food_kg,
  SUM(pet_kg) + SUM(ps_count) * 0.02             AS plastic_kg,
  SUM(plastic_count)                             AS plastic_count,
  SUM(harmful_plastic_count)                     AS harmful_count,
  COLLECT_LIST(plastic_items_json)               AS plastic_jsons,
  AVG(food_kg + pet_kg + ps_count * 0.02)        AS avg_scan_weight
FROM {SCANS_UNIFIED}
WHERE timestamp >= NOW() - INTERVAL 7 DAYS
GROUP BY restaurant_id
"""

SQL_RESTAURANT_PREV_WEEK = f"""
SELECT
  restaurant_id,
  AVG(food_kg + pet_kg + ps_count * 0.02)        AS avg_scan_weight
FROM {SCANS_UNIFIED}
WHERE timestamp BETWEEN NOW() - INTERVAL 14 DAYS
                    AND NOW() - INTERVAL  7 DAYS
GROUP BY restaurant_id
"""

# ZIP averages — pooled across restaurants in the same ZIP (this week)
SQL_ZIP_AVG = f"""
SELECT
  zip,
  AVG(food_kg)                                   AS zip_avg_food_kg,
  AVG(pet_kg + ps_count * 0.02)                  AS zip_avg_plastic_kg
FROM {SCANS_UNIFIED}
WHERE timestamp >= NOW() - INTERVAL 7 DAYS
GROUP BY zip
"""


def _parse_ban_and_recyclable(json_list: list[str]) -> tuple[int, int]:
    """
    Count (banned_items, recyclable_items) across this week's plastic_items_json.

    banned = status startswith 'banned_' (e.g. 'banned_ca' CA SB 54/270/1884)
    recyclable = recyclable == true  (HDPE/PET/PP by CV enrichment)
    """
    banned = 0
    recyclable = 0
    for js in json_list or []:
        if not js:
            continue
        try:
            items = json.loads(js)
            for it in items:
                status = (it.get("status") or "").lower()
                if status.startswith("banned_"):
                    banned += int(it.get("estimated_count") or 1)
                if bool(it.get("recyclable")):
                    recyclable += int(it.get("estimated_count") or 1)
        except (json.JSONDecodeError, TypeError):
            continue
    return banned, recyclable


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    facilities = _load_facilities()
    print(f"CA composting facilities loaded: {len(facilities)}")

    ca_net_cap = _ca_network_capacity()
    print(f"CA network composting capacity: {ca_net_cap} tons/year")

    sd_avg_weekly_kg = _sd_expected_food_kg_per_restaurant_per_week()
    if sd_avg_weekly_kg:
        print(f"SD typical restaurant weekly food waste: {sd_avg_weekly_kg:.0f} kg")

    zip_centroids = _load_sd_zip_centroids()

    # Pull aggregates
    week_rows = fetch_all(SQL_RESTAURANT_WEEK)
    prev_rows = fetch_all(SQL_RESTAURANT_PREV_WEEK)
    zip_rows  = fetch_all(SQL_ZIP_AVG)

    if not week_rows:
        print("No scan rows in last 7 days — nothing to score.")
        return

    prev_map: dict[str, float] = {
        r["restaurant_id"]: float(r.get("avg_scan_weight") or 0)
        for r in prev_rows
    }
    zip_food_avg:    dict[str, float] = {
        r["zip"]: float(r.get("zip_avg_food_kg") or 0) for r in zip_rows
    }
    zip_plastic_avg: dict[str, float] = {
        r["zip"]: float(r.get("zip_avg_plastic_kg") or 0) for r in zip_rows
    }

    now = datetime.now(timezone.utc).isoformat()
    scored: list[dict] = []

    for r in week_rows:
        rid = r["restaurant_id"]
        zip_code = r.get("zip") or ""
        neighborhood = r.get("neighborhood") or zip_code

        food_kg       = float(r.get("food_kg") or 0)
        plastic_kg    = float(r.get("plastic_kg") or 0)
        plastic_count = int(r.get("plastic_count") or 0)
        harmful_count = int(r.get("harmful_count") or 0)
        this_week_avg = float(r.get("avg_scan_weight") or 0)
        last_week_avg = prev_map.get(rid)  # None if no prior week → signal5 = 50

        # Parse plastic_items_json for ban + recyclable counts
        jsons = r.get("plastic_jsons") or []
        if isinstance(jsons, str):
            jsons = [jsons]
        ban_flag_count, recyclable_count = _parse_ban_and_recyclable(jsons)

        # --- Pure spec signals (Person B) ---
        s1, s2, s3, s4, s5, score = compute_all_signals_and_score(
            restaurant_food_kg=food_kg,
            zip_avg_food_kg=zip_food_avg.get(zip_code, food_kg),
            ban_flag_count=ban_flag_count,
            harmful_count=harmful_count,
            recyclable_count=recyclable_count,
            total_plastic_count=plastic_count,
            restaurant_plastic_kg=plastic_kg,
            zip_avg_plastic_kg=zip_plastic_avg.get(zip_code, plastic_kg),
            this_week_avg_scan_weight=this_week_avg,
            last_week_avg_scan_weight=last_week_avg,
        )
        tier_name, tier_emoji, tier_key = tier_for_score(score)
        tip = feedback_message(s1, s2, s3, s4, s5)

        # Nearest facility (UI display only — not scored)
        lat, lng = zip_centroids.get(zip_code, (SD_LAT, SD_LNG))
        f_name, f_km, f_cap = _nearest_facility(lat, lng, facilities)

        scored.append({
            "restaurant_id": rid,
            "zip": zip_code,
            "neighborhood": neighborhood,
            "food_kg": food_kg,
            "s1": s1, "s2": s2, "s3": s3, "s4": s4, "s5": s5,
            "score": score,
            "tier_name": tier_name,
            "tier_emoji": tier_emoji,
            "tier_key": tier_key,
            "tip": tip,
            "facility_name": f_name,
            "facility_km": f_km,
            "facility_capacity": f_cap,
        })

    # PERCENT_RANK within ZIP (UI-only locality ranking)
    zip_groups: dict[str, list[dict]] = defaultdict(list)
    for s in scored:
        zip_groups[s["zip"]].append(s)

    for zip_code, group in zip_groups.items():
        # Rank by score DESC so higher score → higher percentile
        group_sorted = sorted(group, key=lambda x: x["score"])
        n = len(group_sorted)
        for rank_idx, s in enumerate(group_sorted):
            better_than = rank_idx
            percentile = rank_idx / max(n - 1, 1)

            full_msg = (
                f"Score: {round(s['score'])}/100 · {s['tier_emoji']} {s['tier_name']}. "
                f"Better than {better_than} of {n} restaurants in {s['neighborhood']}. "
                f"Tip: {s['tip']}."
            )
            if sd_avg_weekly_kg and s["food_kg"] > 0:
                delta_pct = (s["food_kg"] / sd_avg_weekly_kg - 1.0) * 100
                if delta_pct < -5:
                    full_msg += (
                        f" Weekly food waste ({s['food_kg']:.0f} kg) is "
                        f"{abs(delta_pct):.0f}% below the typical SD restaurant "
                        f"({sd_avg_weekly_kg:.0f} kg)."
                    )
                elif delta_pct > 5:
                    full_msg += (
                        f" Weekly food waste ({s['food_kg']:.0f} kg) is "
                        f"{delta_pct:.0f}% above the typical SD restaurant "
                        f"({sd_avg_weekly_kg:.0f} kg)."
                    )
            if s["facility_name"] and s["facility_km"] is not None:
                full_msg += (
                    f" Nearest composting site: {s['facility_name']} "
                    f"({s['facility_km']:.1f} km)."
                )

            execute(f"""
                UPDATE {INSIGHTS}
                SET
                  sustainability_score           = :score,
                  signal_1                       = :s1,
                  signal_2                       = :s2,
                  signal_3                       = :s3,
                  signal_4                       = :s4,
                  signal_5                       = :s5,
                  badge_tier                     = :tier_name,
                  tier_emoji                     = :tier_emoji,
                  tier_key                       = :tier_key,
                  locality_percentile            = :pct,
                  locality_percentile_pct        = :pct_int,
                  zip_restaurant_count           = :total,
                  better_than_count              = :better,
                  score_feedback_message         = :msg,
                  nearest_facility_name          = :fname,
                  nearest_facility_km            = :fkm,
                  nearest_facility_capacity_tons = :fcap,
                  ca_network_capacity_tons       = :ca_cap
                WHERE restaurant_id = :rid
                  AND computed_at = (
                    SELECT MAX(computed_at) FROM {INSIGHTS}
                    WHERE restaurant_id = :rid
                  )
            """, {
                "score": s["score"],
                "s1": round(s["s1"], 1),
                "s2": round(s["s2"], 1),
                "s3": round(s["s3"], 1),
                "s4": round(s["s4"], 1),
                "s5": round(s["s5"], 1),
                "tier_name": s["tier_name"],
                "tier_emoji": s["tier_emoji"],
                "tier_key": s["tier_key"],
                "pct": round(percentile, 4),
                "pct_int": int(percentile * 100),
                "total": n,
                "better": better_than,
                "msg": full_msg,
                "fname": s["facility_name"],
                "fkm": s["facility_km"],
                "fcap": s["facility_capacity"],
                "ca_cap": ca_net_cap,
                "rid": s["restaurant_id"],
            })

    print(f"✅ Scored {len(scored)} restaurants across {len(zip_groups)} ZIPs "
          f"(ts={now})")
    for s in scored[:10]:
        print(
            f"  {s['restaurant_id'][:22]:22s} | "
            f"{s['score']:5.1f} · {s['tier_emoji']} {s['tier_name']:15s} | "
            f"s1={s['s1']:5.1f} s2={s['s2']:5.1f} s3={s['s3']:5.1f} "
            f"s4={s['s4']:5.1f} s5={s['s5']:5.1f}"
        )


if __name__ == "__main__":
    main()
