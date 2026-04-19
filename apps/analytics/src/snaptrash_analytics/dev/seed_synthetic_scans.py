"""
Synthetic scan seeder — writes realistic restaurant scans to
`workspace.analytics.synthetic_scans` so the rolling aggregation, locality agg,
and per-restaurant Prophet pipelines can run BEFORE the CV team lands real
scans in `workspace.snaptrash.scans`.

DESIGN CONTRACT:
  - We NEVER write to workspace.snaptrash.scans (CV team owns that table).
  - `synthetic_scans` mirrors the SCANS DDL 1:1 so a UNION ALL view
    (`scans_unified`) is seamless.
  - Each synthetic food item carries a `prepped_at` ISO timestamp so the
    shelf-life aggregation can compute `shelf_life_remaining_days`.
  - Deterministic (seeded RNG) so re-runs produce identical rows — idempotent.

Seed scope:
  - 30 restaurants across 15 SD ZIPs (real ZCTAs)
  - 14 days of daily scans (~1 scan/restaurant/day, some noise)
  - Realistic food_kg / plastic counts / $ wastage
"""
from __future__ import annotations

import json
import random
import uuid
from datetime import datetime, timedelta, timezone

from snaptrash_common.databricks_client import execute, fetch_all
from snaptrash_common.tables import SCANS, SYNTH_SCANS, ddl_scans_unified

RNG_SEED = 42
DAYS_BACK = 14
RESTAURANTS_PER_ZIP = 2  # 15 ZIPs × 2 = 30 restaurants

# Real SD ZCTAs + neighborhoods (matches gold_sd_zip_pop entries)
SD_ZIPS: list[tuple[str, str]] = [
    ("92101", "Downtown"),
    ("92103", "Hillcrest"),
    ("92104", "North Park"),
    ("92105", "City Heights"),
    ("92107", "Ocean Beach"),
    ("92109", "Pacific Beach"),
    ("92110", "Old Town"),
    ("92113", "Barrio Logan"),
    ("92115", "College Area"),
    ("92116", "Normal Heights"),
    ("92117", "Clairemont"),
    ("92121", "Sorrento Valley"),
    ("92122", "University City"),
    ("92126", "Mira Mesa"),
    ("92131", "Scripps Ranch"),
]

# Realistic menu item pool — type must match gold_food_prices / gold_food_shelf_life keys
# (type, base_kg, compostable_frac, total_shelf_life_days_usda)
FOOD_POOL: list[tuple[str, float, float, int]] = [
    ("cooked chicken",  0.8, 0.95, 4),
    ("beef",            0.6, 0.90, 3),
    ("fish",            0.4, 0.95, 2),
    ("cooked rice",     1.2, 1.00, 5),
    ("pasta",           0.9, 1.00, 5),
    ("bread",           0.5, 1.00, 7),
    ("leafy greens",    0.7, 1.00, 5),
    ("tomatoes",        0.4, 1.00, 7),
    ("onions",          0.3, 1.00, 60),
    ("potatoes",        0.6, 1.00, 14),
    ("cheese",          0.3, 0.80, 21),
    ("eggs",            0.2, 1.00, 21),
    ("salad",           0.6, 1.00, 3),
    ("soup",            0.4, 1.00, 4),
    ("mixed food",      0.8, 0.85, 3),
]

# Describing-color pool used by Groq Vision — mirrored here for realism
COLOR_POOL = ["beige", "brown", "golden", "red", "green", "orange", "white", "yellow"]

# Plastic items — matches PlasticItem schema exactly
# (base_type, polymer_type, resin_code, status, recyclable, harmful, is_banned_ca)
PLASTIC_POOL: list[tuple[str, str, int | None, str, bool, bool, bool]] = [
    ("water bottle",      "PET",   1,    "recyclable",  True,  False, False),
    ("jug",               "HDPE",  2,    "recyclable",  True,  False, False),
    ("film wrap",         "LDPE",  4,    "recyclable",  True,  False, False),
    ("takeout container", "PP",    5,    "recyclable",  True,  False, False),
    ("foam clamshell",    "PS",    6,    "banned_ca",   False, True,  True),   # CA SB 54
    ("pvc wrap",          "PVC",   3,    "harmful",     False, True,  False),
    ("single-use bag",    "LDPE",  4,    "banned_ca",   False, True,  True),   # CA SB 270
    ("straw",             "PP",    5,    "banned_ca",   False, True,  True),   # CA AB 1884
]


def _mk_food_items(rng: random.Random, scan_ts: datetime) -> tuple[list[dict], float, float, float, float]:
    """
    Generate 2–5 food items matching FoodItem schema exactly (schemas.py).
    Returns (items_list, food_kg, compost_kg, contam_kg, dollar).

    Every field a CV-enriched scan would carry is populated so the
    insights_reader.py LATERAL VIEW explode + rolling aggregation both work
    without null-handling surprises.
    """
    n = rng.randint(2, 5)
    picks = rng.sample(FOOD_POOL, k=n)
    items: list[dict] = []
    food_kg = compost_kg = contam_kg = dollar = 0.0
    for ftype, base_kg, compost_frac, total_shelf_days in picks:
        kg = round(base_kg * rng.uniform(0.6, 1.6), 3)
        # decay_stage 0-5 where ≥3 is contaminated
        decay = rng.choices(
            [0, 1, 2, 3, 4, 5], weights=[25, 30, 20, 15, 7, 3], k=1,
        )[0]
        contaminated = decay >= 3 or rng.random() < 0.05
        compostable = compost_frac > 0.9 and not contaminated
        mold_visible = decay >= 4
        # prepped_at — 0 to 5 days before the scan
        prepped = scan_ts - timedelta(
            hours=rng.randint(2, 5 * 24),
            minutes=rng.randint(0, 59),
        )
        age_days = (scan_ts - prepped).total_seconds() / 86400.0
        shelf_remaining = max(0, round(total_shelf_days - age_days))

        ck = round(kg * (compost_frac if compostable else 0.3) *
                   rng.uniform(0.85, 1.0), 3)
        xc = round(kg - ck if contaminated else kg * rng.uniform(0.0, 0.1), 3)

        item: dict = {
            "type": ftype,
            "decay_stage": decay,
            "color_description": rng.choice(COLOR_POOL),
            "mold_visible": mold_visible,
            "estimated_kg": kg,
            "contaminated": contaminated,
            "compostable": compostable,
            "wcs_category": None,             # analytics maps via _WCS_CATEGORY_MAP
            "prepped_at": prepped.isoformat(),
            "shelf_life_remaining_days": shelf_remaining,
            "co2_kg": round(kg * 2.5, 3),     # crude 2.5 kg CO2/kg food
        }
        # dollar_value omitted ~30% of the time so analytics USDA fallback fires
        if rng.random() < 0.7:
            item["dollar_value"] = round(kg * rng.uniform(6, 18), 2)
            dollar += item["dollar_value"]
        else:
            item["dollar_value"] = None
        items.append(item)
        food_kg += kg
        compost_kg += ck
        contam_kg += max(0.0, xc)
    return items, round(food_kg, 3), round(compost_kg, 3), round(contam_kg, 3), round(dollar, 2)


def _mk_plastic_items(rng: random.Random) -> tuple[list[dict], int, int, float, int]:
    """
    Generate 1–4 plastic items matching PlasticItem schema exactly.
    Returns (items, count, harmful_count, pet_kg, ps_count).
    """
    n = rng.randint(1, 4)
    picks = rng.choices(PLASTIC_POOL, k=n)
    items: list[dict] = []
    total = harmful = ps = 0
    pet_kg = 0.0
    for base_type, polymer, resin, status, recyclable, is_harmful, is_banned in picks:
        count = rng.randint(1, 15)
        is_black = rng.random() < 0.1  # ~10% black plastic (IR-invisible)
        alert = None
        if is_banned:
            alert = f"{polymer} banned in CA — switch to compostable alternative"
        elif is_harmful:
            alert = f"{polymer} is non-recyclable — reduce usage"
        item = {
            "type": base_type,
            "resin_code": resin,
            "color": "black" if is_black else rng.choice(
                ["clear", "white", "green", "blue"]
            ),
            "is_black_plastic": is_black,
            "estimated_count": count,
            "polymer_type": polymer,
            "status": status,
            "recyclable": recyclable,
            "harmful": is_harmful,
            "alert": alert,
        }
        items.append(item)
        total += count
        if is_harmful:
            harmful += count
        if polymer == "PET":
            pet_kg += count * 0.02    # ~20g per PET item
        if polymer == "PS":
            ps += count
    return items, total, harmful, round(pet_kg, 3), ps


def _build_rows(rng: random.Random) -> list[dict]:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    rows: list[dict] = []
    # Build stable restaurant roster
    restaurants = []
    for zip_code, nb in SD_ZIPS:
        for i in range(RESTAURANTS_PER_ZIP):
            rid = f"synth-{zip_code}-{i+1:02d}"
            restaurants.append((rid, zip_code, nb))

    for day_offset in range(DAYS_BACK, 0, -1):
        for rid, zip_code, nb in restaurants:
            # ~80% of restaurants scan on any given day (adds realistic gaps)
            if rng.random() > 0.8:
                continue
            # 1–2 scans/day per active restaurant
            for _ in range(rng.randint(1, 2)):
                scan_ts = now - timedelta(
                    days=day_offset,
                    hours=rng.randint(0, 23),
                    minutes=rng.randint(0, 59),
                )
                food_items, food_kg, compost_kg, contam_kg, dollar = _mk_food_items(rng, scan_ts)
                plastic_items, pcount, harmful, pet_kg, ps = _mk_plastic_items(rng)
                co2 = round(food_kg * 2.5 + pet_kg * 6.0, 3)  # rough

                rows.append({
                    "scan_id": str(uuid.uuid4()),
                    "restaurant_id": rid,
                    "zip": zip_code,
                    "neighborhood": nb,
                    "timestamp": scan_ts.isoformat(),
                    "food_kg": food_kg,
                    "compostable_kg": compost_kg,
                    "contaminated_kg": contam_kg,
                    "dollar_wastage": dollar,
                    "co2_kg": co2,
                    "plastic_count": pcount,
                    "harmful_plastic_count": harmful,
                    "pet_kg": pet_kg,
                    "ps_count": ps,
                    "food_items_json": json.dumps(food_items),
                    "plastic_items_json": json.dumps(plastic_items),
                })
    return rows


def _ensure_table() -> None:
    """Create synthetic_scans mirroring SCANS DDL (minus partitioning to keep simple)."""
    execute(f"DROP TABLE IF EXISTS {SYNTH_SCANS}")
    execute(f"""
        CREATE TABLE {SYNTH_SCANS} (
            scan_id                 STRING,
            restaurant_id           STRING,
            zip                     STRING,
            neighborhood            STRING,
            timestamp               TIMESTAMP,
            food_kg                 DOUBLE,
            compostable_kg          DOUBLE,
            contaminated_kg         DOUBLE,
            dollar_wastage          DOUBLE,
            co2_kg                  DOUBLE,
            plastic_count           INT,
            harmful_plastic_count   INT,
            pet_kg                  DOUBLE,
            ps_count                INT,
            total_plastic_kg        DOUBLE,
            ban_flag_count          INT,
            recyclable_count        INT,
            food_items_json         STRING,
            plastic_items_json      STRING
        ) USING DELTA
    """)


def _q(s: str) -> str:
    """SQL-string escape: ' → ''."""
    return s.replace("'", "''")


def _insert_rows(rows: list[dict]) -> None:
    # Chunked multi-row INSERT — Databricks SQL Statement API tolerates large payloads
    # but keep chunks < 500 rows to stay under body-size caps.
    CHUNK = 250
    for i in range(0, len(rows), CHUNK):
        chunk = rows[i:i + CHUNK]
        values_sql = ",\n".join(
            "("
            f"'{r['scan_id']}',"
            f"'{r['restaurant_id']}',"
            f"'{r['zip']}',"
            f"'{_q(r['neighborhood'])}',"
            f"TIMESTAMP'{r['timestamp']}',"
            f"{r['food_kg']},{r['compostable_kg']},{r['contaminated_kg']},"
            f"{r['dollar_wastage']},{r['co2_kg']},"
            f"{r['plastic_count']},{r['harmful_plastic_count']},"
            f"{r['pet_kg']},{r['ps_count']},"
            f"{r.get('total_plastic_kg', 0.0)},{r.get('ban_flag_count', 0)},{r.get('recyclable_count', 0)},"
            f"'{_q(r['food_items_json'])}',"
            f"'{_q(r['plastic_items_json'])}'"
            ")"
            for r in chunk
        )
        execute(f"INSERT INTO {SYNTH_SCANS} VALUES {values_sql}")


def main() -> int:
    rng = random.Random(RNG_SEED)
    _ensure_table()
    rows = _build_rows(rng)
    if not rows:
        print("No synthetic rows generated — check DAYS_BACK / SD_ZIPS.")
        return 0
    _insert_rows(rows)

    n = fetch_all(f"SELECT COUNT(*) AS n FROM {SYNTH_SCANS}")
    distinct = fetch_all(
        f"SELECT COUNT(DISTINCT restaurant_id) AS n, "
        f"COUNT(DISTINCT zip) AS z FROM {SYNTH_SCANS}"
    )
    print(f"✅ synthetic_scans: {int(n[0]['n'])} rows, "
          f"{int(distinct[0]['n'])} restaurants, "
          f"{int(distinct[0]['z'])} ZIPs")

    # Sanity: compare against real scans table so user sees demo coverage.
    try:
        real = fetch_all(f"SELECT COUNT(*) AS n FROM {SCANS}")
        print(f"   (real snaptrash.scans row count: {int(real[0]['n'])})")
    except Exception:
        pass

    # Rebuild scans_unified UNION ALL view now that SYNTH_SCANS is populated.
    execute(ddl_scans_unified())
    print("✅ scans_unified view rebuilt")

    return len(rows)


if __name__ == "__main__":
    main()
