"""
Load gold reference tables from workspace.hackathon Dryad data.
Run ONCE at hackathon start (or re-run to refresh).

Gold tables produced:
  snaptrash.gold_wcs_benchmark       — CA commercial waste % by material
  snaptrash.gold_sd_disposal_ts      — SD county per-capita disposal 2015-2019
  snaptrash.gold_composting_routes_ca — CA facilities sorted by distance from SD
"""
from __future__ import annotations
from snaptrash_common.databricks_client import execute, fetch_all
from snaptrash_common.geo import haversine
from snaptrash_common.tables import (
    GOLD_WCS, GOLD_SD_DISPOSAL, GOLD_COMPOSTING,
    GOLD_CA_CAPACITY, GOLD_SD_POPULATION, GOLD_SD_COMMERCIAL,
)

HACKATHON = "workspace.hackathon"

# San Diego city center coordinates
SD_LAT = 32.7157
SD_LNG = -117.1611


# ---------------------------------------------------------------------------
# Haversine distance (km)
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# 1. gold_wcs_benchmark — CA commercial waste % by material (latest year)
# ---------------------------------------------------------------------------

def load_wcs_benchmark() -> int:
    """
    Materializes CA commercial waste benchmark from wcs_2.
    Result row example:
      material='food', year=2021, tons=2808570, state_total_tons=15861299, material_pct=17.7
    """
    rows = fetch_all(f"""
        WITH latest AS (
            SELECT MAX(CAST(year AS INT)) AS max_year
            FROM {HACKATHON}.wcs_2
            WHERE state_id = 'CA'
              AND generator_category = 'commercial'
              AND need_to_find IS NULL
              AND tons IS NOT NULL
        ),
        agg AS (
            SELECT
                material,
                CAST(year AS INT) AS year,
                AVG(CAST(tons AS DOUBLE)) AS tons
            FROM {HACKATHON}.wcs_2, latest
            WHERE state_id = 'CA'
              AND generator_category = 'commercial'
              AND need_to_find IS NULL
              AND tons IS NOT NULL
              AND CAST(year AS INT) = max_year
            GROUP BY material, year
        ),
        totals AS (
            SELECT SUM(tons) AS state_total_tons FROM agg WHERE material != 'total'
        )
        SELECT
            a.material, a.year, a.tons,
            t.state_total_tons,
            ROUND(a.tons / t.state_total_tons * 100, 2) AS material_pct
        FROM agg a CROSS JOIN totals t
        WHERE a.material != 'total'
        ORDER BY a.tons DESC
    """)

    execute(f"DELETE FROM {GOLD_WCS}")
    for r in rows:
        execute(
            f"INSERT INTO {GOLD_WCS} VALUES (:material, :year, :tons, :state_total, :pct)",
            {
                "material": r["material"],
                "year": int(r["year"]),
                "tons": float(r["tons"]),
                "state_total": float(r["state_total_tons"]),
                "pct": float(r["material_pct"]),
            },
        )
    print(f"  gold_wcs_benchmark: {len(rows)} materials loaded")
    for r in rows:
        print(f"    {r['material']:35s} {float(r['material_pct']):5.1f}%  ({float(r['tons'])/1e6:.2f}M tons)")
    return len(rows)


# ---------------------------------------------------------------------------
# 2. gold_sd_disposal_ts — SD county per-capita disposal time series 2015-2019
# ---------------------------------------------------------------------------

def load_sd_disposal_ts() -> int:
    """
    Per-capita disposal for San Diego county 2015-2019.
    Joins SD population from gold_sd_population (no hardcoded dict).
    Used as the benchmark in the locality popup and per-capita map.
    """
    rows = fetch_all(f"""
        WITH d AS (
            SELECT CAST(year AS INT) AS year,
                   county_name        AS county,
                   SUM(CAST(tons AS DOUBLE)) AS disposal_tons
            FROM {HACKATHON}.power2_impexp
            WHERE state_id = 'CA'
              AND LOWER(county_name) = 'san diego'
              AND LOWER(type) = 'disposal'
              AND CAST(year AS INT) BETWEEN 2015 AND 2019
            GROUP BY year, county_name
        )
        SELECT d.year, d.county, d.disposal_tons, p.population
        FROM d JOIN {GOLD_SD_POPULATION} p USING (year)
        ORDER BY d.year
    """)

    execute(f"DELETE FROM {GOLD_SD_DISPOSAL}")
    for r in rows:
        yr = int(r["year"])
        pop = int(r["population"])
        disposal_tons = float(r["disposal_tons"])
        per_capita_kg = disposal_tons * 907.185 / pop  # tons→kg / population
        execute(
            f"INSERT INTO {GOLD_SD_DISPOSAL} VALUES (:year, :county, :tons, :pop, :per_cap)",
            {
                "year": yr,
                "county": r["county"],
                "tons": disposal_tons,
                "pop": pop,
                "per_cap": round(per_capita_kg, 2),
            },
        )
        print(f"    {yr}: {per_capita_kg:.0f} kg/person/yr")
    print(f"  gold_sd_disposal_ts: {len(rows)} years loaded")
    return len(rows)


# ---------------------------------------------------------------------------
# 3. gold_composting_routes_ca — CA facilities sorted by distance from SD
# ---------------------------------------------------------------------------

def load_composting_routes() -> int:
    """
    Reads CA composting facilities from Dryad data, computes haversine distance
    from SD city center, and stores sorted. Used for nearest-facility recommendation.
    """
    rows = fetch_all(f"""
        SELECT
            composting_facility AS facility_name,
            CAST(lat AS DOUBLE) AS lat,
            CAST(long AS DOUBLE) AS lng,
            CAST(capacity AS DOUBLE) AS capacity_tons
        FROM {HACKATHON}.composting_infrastructure_all_states_gov
        WHERE state_name = 'California'
          AND lat IS NOT NULL
          AND long IS NOT NULL
        ORDER BY facility_name
    """)

    facilities = []
    for r in rows:
        try:
            lat = float(r["lat"])
            lng = float(r["lng"])
            dist = haversine(SD_LAT, SD_LNG, lat, lng)
            facilities.append({
                "name": r["facility_name"],
                "lat": lat,
                "lng": lng,
                "capacity": float(r["capacity_tons"]) if r["capacity_tons"] else 0.0,
                "dist_km": round(dist, 2),
            })
        except (TypeError, ValueError):
            continue

    facilities.sort(key=lambda x: x["dist_km"])

    execute(f"DELETE FROM {GOLD_COMPOSTING}")
    for f in facilities:
        execute(
            f"INSERT INTO {GOLD_COMPOSTING} VALUES (:name, :lat, :lng, :cap, :dist)",
            {
                "name": f["name"],
                "lat": f["lat"],
                "lng": f["lng"],
                "cap": f["capacity"],
                "dist": f["dist_km"],
            },
        )
    print(f"  gold_composting_routes_ca: {len(facilities)} CA facilities loaded")
    print(f"  Nearest 3 to SD:")
    for f in facilities[:3]:
        print(f"    {f['name'][:45]:45s} {f['dist_km']:6.1f} km")
    return len(facilities)


# ---------------------------------------------------------------------------
# 4. gold_ca_composting_capacity — statewide CA composting network capacity
# ---------------------------------------------------------------------------

def load_ca_composting_capacity() -> int:
    """Statewide CA composting network capacity (tons/year), latest year row."""
    execute(f"DROP TABLE IF EXISTS {GOLD_CA_CAPACITY}")
    execute(f"""
        CREATE TABLE {GOLD_CA_CAPACITY} USING DELTA AS
        SELECT state_id,
               CAST(capacity AS BIGINT) AS annual_capacity_tons,
               CAST(year AS INT)        AS year
        FROM {HACKATHON}.composting_capacity_all_states
        WHERE state_id = 'CA'
        QUALIFY ROW_NUMBER() OVER (ORDER BY CAST(year AS INT) DESC) = 1
    """)
    rows = fetch_all(f"SELECT * FROM {GOLD_CA_CAPACITY}")
    if rows:
        r = rows[0]
        print(f"  gold_ca_composting_capacity: CA = {int(r['annual_capacity_tons']):,} tons/yr ({r['year']})")
    return len(rows)


# ---------------------------------------------------------------------------
# 5. gold_sd_population — SD county population 2017–2019 (from population.csv)
# ---------------------------------------------------------------------------

def load_sd_population() -> int:
    """SD county pop by year (long format 2015-2019) — denominator for per-capita metrics."""
    execute(f"DROP TABLE IF EXISTS {GOLD_SD_POPULATION}")
    execute(f"""
        CREATE TABLE {GOLD_SD_POPULATION} USING DELTA AS
        SELECT yr.year, CAST(
            CASE yr.year
                WHEN 2015 THEN `2015` WHEN 2016 THEN `2016`
                WHEN 2017 THEN `2017` WHEN 2018 THEN `2018`
                WHEN 2019 THEN `2019`
            END AS INT) AS population
        FROM {HACKATHON}.population
        LATERAL VIEW explode(array(2015,2016,2017,2018,2019)) yr AS year
        WHERE State = 'CA' AND LOWER(County) = 'san diego'
    """)
    rows = fetch_all(f"SELECT year, population FROM {GOLD_SD_POPULATION} ORDER BY year")
    for r in rows:
        print(f"    {int(r['year'])}: {int(r['population']):,}")
    print(f"  gold_sd_population: {len(rows)} years")
    return len(rows)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 6. gold_sd_commercial_benchmark — SD commercial waste by material (derived)
#    SD_county_disposal_tons × CA_commercial_share_pct
# ---------------------------------------------------------------------------

def load_sd_commercial_benchmark() -> int:
    """
    Derives SD-specific commercial waste per material:
      SD_commercial_tons = SD_county_total_disposal × CA_commercial_share(material)
    Source: latest-year power2_impexp (SD) × wcs_2 CA commercial % (from gold_wcs_benchmark).
    """
    execute(f"DROP TABLE IF EXISTS {GOLD_SD_COMMERCIAL}")
    execute(f"""
        CREATE TABLE {GOLD_SD_COMMERCIAL} USING DELTA AS
        WITH sd_latest AS (
            SELECT year, disposal_tons
            FROM {GOLD_SD_DISPOSAL}
            ORDER BY year DESC LIMIT 1
        )
        SELECT
            w.material,
            sd.year                                         AS sd_year,
            w.year                                          AS wcs_year,
            sd.disposal_tons                                AS sd_county_disposal_tons,
            w.material_pct                                  AS ca_commercial_pct,
            ROUND(sd.disposal_tons * w.material_pct / 100.0, 2) AS sd_commercial_tons
        FROM {GOLD_WCS} w CROSS JOIN sd_latest sd
    """)
    rows = fetch_all(f"SELECT material, sd_commercial_tons FROM {GOLD_SD_COMMERCIAL} ORDER BY sd_commercial_tons DESC")
    print(f"  gold_sd_commercial_benchmark: {len(rows)} materials derived")
    for r in rows[:5]:
        print(f"    {r['material']:35s} {float(r['sd_commercial_tons'])/1e3:7.1f}K tons/yr")
    return len(rows)


def main():
    print("Loading gold reference tables from Dryad data...\n")

    print("[1/6] WCS benchmark (wcs_2 → CA commercial %)")
    load_wcs_benchmark()

    print("\n[2/6] SD county population (population)")
    load_sd_population()

    print("\n[3/6] SD county disposal time series (power2_impexp + gold_sd_population)")
    load_sd_disposal_ts()

    print("\n[4/6] CA composting routes (composting_infrastructure)")
    load_composting_routes()

    print("\n[5/6] CA composting network capacity (composting_capacity_all_states)")
    load_ca_composting_capacity()

    print("\n[6/6] SD commercial benchmark (derived: SD disposal × CA commercial %)")
    load_sd_commercial_benchmark()

    print("\n✅ Gold tables ready.")


if __name__ == "__main__":
    main()
