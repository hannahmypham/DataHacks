"""Pre-load 4 weeks of fake restaurant scans for demo (Hour 18-20).

Generates ~280 rows across 5 restaurants in San Diego ZIPs.
"""
from __future__ import annotations
import json
import random
import uuid
from datetime import datetime, timedelta, timezone

from snaptrash_common.databricks_client import execute
from snaptrash_common.tables import SCANS

random.seed(42)

RESTAURANTS = [
    ("rest_001", "92037", "La Jolla"),
    ("rest_002", "92104", "North Park"),
    ("rest_003", "92103", "Hillcrest"),
    ("rest_004", "92101", "Downtown"),
    ("rest_005", "92109", "Pacific Beach"),
]

FOOD_TYPES = ["leafy greens", "raw chicken", "cooked rice", "bread", "fish", "vegetables"]
PLASTIC_TYPES = [
    ("foam container", 6, "PS"),
    ("water bottle", 1, "PET"),
    ("cling wrap", 4, "LDPE"),
    ("yogurt cup", 5, "PP"),
]

INSERT = f"""
INSERT INTO {SCANS} VALUES (
  :scan_id, :restaurant_id, :zip, :neighborhood, :timestamp,
  :food_kg, :compostable_kg, :contaminated_kg,
  :dollar_wastage, :co2_kg,
  :plastic_count, :harmful_plastic_count,
  :pet_kg, :ps_count, :total_plastic_kg, :ban_flag_count, :recyclable_count,
  :food_items_json, :plastic_items_json
)
"""


def fake_scan(rid: str, zipc: str, nb: str, ts: datetime) -> dict:
    food_kg = round(random.uniform(0.3, 5.0), 2)
    compost = round(food_kg * random.uniform(0.4, 0.85), 2)
    contam = round(food_kg - compost, 2)
    dollars = round(food_kg * random.uniform(3.0, 12.0), 2)
    co2 = round(food_kg * random.uniform(1.5, 8.0), 2)
    plastic_n = random.randint(0, 8)
    pkinds = random.sample(PLASTIC_TYPES, k=min(plastic_n, len(PLASTIC_TYPES))) if plastic_n else []
    ps = sum(1 for _, _, p in pkinds if p == "PS")
    pet = round(0.05 * sum(1 for _, _, p in pkinds if p == "PET"), 2)
    harmful = ps
    total_plastic = round(plastic_n * 0.12 + pet * 2, 2)
    ban_flag = random.randint(0, max(1, plastic_n // 3))
    recyclable = max(0, plastic_n - harmful - ban_flag)
    return {
        "scan_id": str(uuid.uuid4()),
        "restaurant_id": rid,
        "zip": zipc,
        "neighborhood": nb,
        "timestamp": ts.isoformat(),
        "food_kg": food_kg,
        "compostable_kg": compost,
        "contaminated_kg": contam,
        "dollar_wastage": dollars,
        "co2_kg": co2,
        "plastic_count": plastic_n,
        "harmful_plastic_count": harmful,
        "pet_kg": pet,
        "ps_count": ps,
        "total_plastic_kg": total_plastic,
        "ban_flag_count": ban_flag,
        "recyclable_count": recyclable,
        "food_items_json": json.dumps([{"type": random.choice(FOOD_TYPES), "estimated_kg": food_kg, "decay_stage": random.randint(1,5), "contaminated": contam > 0.3}]),
        "plastic_items_json": json.dumps([{"type": t, "resin_code": rc, "polymer_type": pt, "estimated_kg": round(0.15,2)} for t, rc, pt in pkinds]),
    }


def main():
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=28)
    inserted = 0
    for rid, zipc, nb in RESTAURANTS:
        cur = start
        while cur < end:
            for _ in range(random.randint(1, 3)):
                row = fake_scan(rid, zipc, nb, cur)
                execute(INSERT, row)
                inserted += 1
            cur += timedelta(days=1)
    print(f"✅ seeded {inserted} fake scans across {len(RESTAURANTS)} restaurants")


if __name__ == "__main__":
    main()
