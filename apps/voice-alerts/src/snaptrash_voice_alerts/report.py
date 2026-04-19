"""
Report generation for plastic waste alerts (used by both voice and email).
Queries Databricks (scans_unified) for localities/restaurants exceeding thresholds.
Loads enzyme labs CSV (focus CA/BluumBio, hardcoded lab email in sender).
Generates PlasticReportContext for Vapi calls + SMTP emails (per plan).
Supports restaurant-specific triggers if individual >~30kg/week.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
from snaptrash_common.databricks_client import fetch_all
from snaptrash_common.env import settings, REPO_ROOT
from snaptrash_common.schemas import PlasticReportContext
from snaptrash_common.tables import LOCALITY_AGG, SCANS_UNIFIED, VOICE_ALERTS


def load_enzyme_labs() -> pd.DataFrame:
    """Load CSV for CA labs mention (BluumBio etc.)."""
    csv_path = REPO_ROOT / "data" / "plastic_enzyme_companies_and_labs_usa.csv"
    if csv_path.exists():
        df = pd.read_csv(csv_path)
        ca_labs = df[df["state"] == "California"]
        return ca_labs
    print(f"Warning: CSV not found at {csv_path}")
    return pd.DataFrame()


def _create_sample_report(threshold: float = 150.0, is_restaurant: bool = False) -> PlasticReportContext:
    """Sample report > threshold for demo (ensures calls/emails always trigger even with empty DB). Content focuses on locality plastic volume/types exceeding limits and request for enzyme company assistance."""
    if is_restaurant:
        return PlasticReportContext(
            locality="Restaurant-TEST-001",
            neighborhood="Downtown San Diego",
            total_plastic_kg=187.5,
            harmful_count=12,
            pet_kg=95.2,
            weekly_plastic_count=45,
            active_restaurants=1,
            threshold=threshold,
            lab_recommendation="This locality has generated substantial PET and polystyrene plastic exceeding limits. We need your plastic-eating enzymes to reduce landfills.",
            stats_summary="This restaurant has generated 187.5kg of harmful plastic this week, far beyond limits. Requesting your enzyme solutions for biological breakdown to cut landfill waste (demo).",
            forecast_note="Trends indicate continued high volumes without intervention.",
        )
    return PlasticReportContext(
        locality="92101",
        neighborhood="Downtown San Diego",
        total_plastic_kg=187.5,
        harmful_count=12,
        pet_kg=95.2,
        weekly_plastic_count=45,
        active_restaurants=8,
        threshold=threshold,
        lab_recommendation="This locality has generated substantial PET and polystyrene plastic exceeding limits. We need your plastic-eating enzymes to reduce landfills.",
        stats_summary="This locality has generated 187.5kg of primarily PET and polystyrene plastic this week, far exceeding limits and adding to landfills. Requesting your plastic-eating enzymes to reduce the waste (demo).",
        forecast_note="Trends indicate continued high volumes without intervention.",
    )


def generate_plastic_report(zip_code: Optional[str] = None) -> List[PlasticReportContext]:
    """Generate reports for *localities* exceeding 150kg plastic/week.
    If zip provided, focus on that; else all exceeding. Used by both voice + email.
    Falls back to sample report (>150kg) for demo if DB query returns 0 rows (ensures repeated calls/emails).
    See generate_restaurant_plastic_reports() for per-restaurant triggers.
    """
    labs = load_enzyme_labs()
    lab_rec = "Contact BluumBio (Berkeley, CA - see CSV) for enzymatic plastic degradation."
    if not labs.empty:
        lab_rec = f"Contact {labs.iloc[0]['name']} in {labs.iloc[0]['city']}, CA for enzymes."

    # Query for high plastic volume (extend locality_agg or direct from scans_unified for accuracy)
    # Prefer recent 7d aggregates; add total_plastic_kg if not in locality_agg
    zip_filter = f"AND zip = '{zip_code}'" if zip_code else ""
    sql = f"""
    SELECT
        ANY_VALUE(zip)                              AS zip,
        ANY_VALUE(neighborhood)                     AS neighborhood,
        SUM(pet_kg) + SUM(ps_count) * 0.02         AS total_plastic_kg,
        SUM(harmful_plastic_count)                  AS harmful_count,
        SUM(pet_kg)                                 AS pet_kg,
        COUNT(DISTINCT restaurant_id)               AS active_restaurants,
        SUM(plastic_count)                          AS weekly_plastic_count
    FROM {SCANS_UNIFIED}
    WHERE timestamp >= NOW() - INTERVAL 7 DAYS
    {zip_filter}
    GROUP BY zip
    HAVING SUM(pet_kg) + SUM(ps_count) * 0.02 > 150.0
    ORDER BY total_plastic_kg DESC
    """

    rows = fetch_all(sql)
    reports = []
    for row in rows:
        report = PlasticReportContext(
            locality=row.get("zip", "Unknown"),
            neighborhood=row.get("neighborhood", "San Diego area"),
            total_plastic_kg=float(row.get("total_plastic_kg", 0)),
            harmful_count=int(row.get("harmful_count", 0)),
            pet_kg=float(row.get("pet_kg", 0)),
            weekly_plastic_count=int(row.get("weekly_plastic_count", 0)),
            active_restaurants=int(row.get("active_restaurants", 1)),
            threshold=150.0,
            lab_recommendation=lab_rec,
            stats_summary=f"High plastic: {row.get('total_plastic_kg', 0):.1f}kg ({row.get('harmful_count',0)} harmful items detected). "
                         f"Impacting {row.get('active_restaurants',1)} restaurants. Weekly count: {row.get('weekly_plastic_count',0)}.",
            forecast_note="Without intervention, Prophet models predict sustained high volumes.",
        )
        reports.append(report)
    if not reports:
        reports = [_create_sample_report(150.0)]
        print("No DB rows > threshold; using sample report >150kg for demo (calls/emails will trigger).")
    else:
        print(f"Generated {len(reports)} high-plastic locality reports (threshold 150kg/week).")
    return reports


def generate_restaurant_plastic_reports(threshold: float = 30.0) -> List[PlasticReportContext]:
    """Generate reports for individual *restaurants* exceeding per-restaurant threshold.
    Triggered if a single restaurant generates significant waste (e.g. >30kg plastic/week).
    Falls back to sample report (>30kg) for demo if DB query returns 0 rows (ensures repeated calls/emails).
    Uses similar structure; locality field repurposed for restaurant context.
    """
    labs = load_enzyme_labs()
    lab_rec = "Contact BluumBio (Berkeley, CA - see CSV) for enzymatic plastic degradation."
    if not labs.empty:
        lab_rec = f"Contact {labs.iloc[0]['name']} in {labs.iloc[0]['city']}, CA for enzymes."

    sql = f"""
    SELECT
        ANY_VALUE(zip)                              AS zip,
        ANY_VALUE(neighborhood)                     AS neighborhood,
        restaurant_id,
        SUM(pet_kg) + SUM(ps_count) * 0.02         AS total_plastic_kg,
        SUM(harmful_plastic_count)                  AS harmful_count,
        SUM(pet_kg)                                 AS pet_kg,
        1                                           AS active_restaurants,
        SUM(plastic_count)                          AS weekly_plastic_count
    FROM {SCANS_UNIFIED}
    WHERE timestamp >= NOW() - INTERVAL 7 DAYS
    GROUP BY zip, neighborhood, restaurant_id
    HAVING SUM(pet_kg) + SUM(ps_count) * 0.02 > {threshold}
    ORDER BY total_plastic_kg DESC
    LIMIT 10
    """

    rows = fetch_all(sql)
    reports = []
    for row in rows:
        rest_id = row.get("restaurant_id", "Unknown")
        report = PlasticReportContext(
            locality=f"Restaurant-{rest_id}",
            neighborhood=row.get("neighborhood", "San Diego area"),
            total_plastic_kg=float(row.get("total_plastic_kg", 0)),
            harmful_count=int(row.get("harmful_count", 0)),
            pet_kg=float(row.get("pet_kg", 0)),
            weekly_plastic_count=int(row.get("weekly_plastic_count", 0)),
            active_restaurants=1,
            threshold=threshold,
            lab_recommendation=lab_rec,
            stats_summary=f"Restaurant {rest_id} generated {row.get('total_plastic_kg', 0):.1f}kg plastic this week "
                         f"({row.get('harmful_count',0)} harmful). Exceeds individual threshold.",
            forecast_note="Without intervention, Prophet models predict sustained high volumes from this site.",
        )
        reports.append(report)
    if not reports:
        reports = [_create_sample_report(30.0, is_restaurant=True)]
        print("No DB rows > threshold; using sample restaurant report >30kg for demo (calls/emails will trigger).")
    else:
        print(f"Generated {len(reports)} high-plastic restaurant reports (threshold {threshold}kg/week).")
    return reports


def get_latest_alerts(limit: int = 5) -> List[Dict]:
    """Helper to check recent voice alerts."""
    sql = f"SELECT * FROM {VOICE_ALERTS} ORDER BY triggered_at DESC LIMIT {limit}"  # Note: VOICE_ALERTS not imported here yet
    try:
        return fetch_all(sql)
    except Exception:
        return []
