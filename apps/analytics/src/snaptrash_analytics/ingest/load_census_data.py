"""
Census API ingestion → per-ZIP population + NAICS 722 (Food Services) establishments.

Gold tables produced:
  snaptrash.analytics.gold_sd_zip_pop           — per-ZIP pop (ACS 2021 5-yr)
  snaptrash.analytics.gold_sd_restaurant_count  — NAICS 722 establishments per ZIP (ZBP 2018)

Run ONCE at hackathon start. Free keyless endpoints; ~150 ZIPs × 2 calls ~ 300 requests.
"""
from __future__ import annotations
import time
import urllib.request
import urllib.error
import json

from snaptrash_common.databricks_client import execute, fetch_all
from snaptrash_common.tables import (
    GOLD_SD_ZIP_POP, GOLD_SD_RESTAURANTS,
)

HACKATHON = "workspace.hackathon"
ACS_URL = "https://api.census.gov/data/2021/acs/acs5"
ZBP_URL = "https://api.census.gov/data/2018/zbp"


def _sd_zips() -> list[str]:
    rows = fetch_all(f"""
        SELECT DISTINCT explode(split(zips, ' ')) AS zip
        FROM {HACKATHON}.uscities
        WHERE county_fips='6073' AND state_id='CA'
        ORDER BY zip
    """)
    return [r["zip"] for r in rows if r["zip"]]


def _get(url: str, retries: int = 3) -> list | None:
    for i in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=10) as r:
                return json.loads(r.read())
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
            if i == retries - 1:
                return None
            time.sleep(1 + i)
    return None


def load_sd_zip_pop() -> int:
    """ACS 2021 B01003_001E (total pop) per SD ZIP."""
    zips = _sd_zips()
    execute(f"DROP TABLE IF EXISTS {GOLD_SD_ZIP_POP}")
    execute(f"""
        CREATE TABLE {GOLD_SD_ZIP_POP} (
            zip STRING,
            population INT
        ) USING DELTA
    """)
    n_ok = 0
    for z in zips:
        url = f"{ACS_URL}?get=B01003_001E&for=zip%20code%20tabulation%20area:{z}"
        data = _get(url)
        if not data or len(data) < 2:
            continue
        try:
            pop = int(data[1][0])
        except (ValueError, IndexError):
            continue
        execute(
            f"INSERT INTO {GOLD_SD_ZIP_POP} VALUES (:zip, :pop)",
            {"zip": z, "pop": pop},
        )
        n_ok += 1
    print(f"  gold_sd_zip_pop: {n_ok}/{len(zips)} ZIPs loaded")
    return n_ok


def load_sd_restaurant_count() -> int:
    """Census ZBP 2018 NAICS 722 (Food Services) establishment count per SD ZIP."""
    zips = _sd_zips()
    execute(f"DROP TABLE IF EXISTS {GOLD_SD_RESTAURANTS}")
    execute(f"""
        CREATE TABLE {GOLD_SD_RESTAURANTS} (
            zip STRING,
            restaurant_count INT
        ) USING DELTA
    """)
    n_ok = 0
    total = 0
    for z in zips:
        url = f"{ZBP_URL}?get=ESTAB&for=zip%20code:{z}&NAICS2017=722"
        data = _get(url)
        if not data or len(data) < 2:
            # Fallback heuristic: pop/500
            continue
        try:
            est = int(data[1][0])
        except (ValueError, IndexError):
            continue
        execute(
            f"INSERT INTO {GOLD_SD_RESTAURANTS} VALUES (:zip, :n)",
            {"zip": z, "n": est},
        )
        n_ok += 1
        total += est

    # Backfill missing ZIPs from pop/500 heuristic
    rows = fetch_all(f"""
        SELECT p.zip, p.population
        FROM {GOLD_SD_ZIP_POP} p
        LEFT JOIN {GOLD_SD_RESTAURANTS} r USING (zip)
        WHERE r.zip IS NULL
    """)
    for r in rows:
        est = max(1, int(r["population"]) // 500)
        execute(
            f"INSERT INTO {GOLD_SD_RESTAURANTS} VALUES (:zip, :n)",
            {"zip": r["zip"], "n": est},
        )
        total += est
    print(f"  gold_sd_restaurant_count: {n_ok} from Census + {len(rows)} heuristic "
          f"= {total:,} total SD food-service establishments")
    return n_ok + len(rows)


def main():
    print("Loading Census-derived gold tables...\n")
    print("[1/2] SD per-ZIP population (ACS 2021)")
    load_sd_zip_pop()
    print("\n[2/2] SD per-ZIP restaurant count (ZBP 2018 NAICS 722)")
    load_sd_restaurant_count()
    print("\n✅ Census gold tables ready.")


if __name__ == "__main__":
    main()
