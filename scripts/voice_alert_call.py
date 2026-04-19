#!/usr/bin/env python3
"""
Small standalone script to automatically trigger a Vapi voice alert call.
**Run with:** uv run --project apps/voice-alerts python scripts/voice_alert_call.py
(or python -m snaptrash_voice_alerts.trigger for full check).
Uses sample high-plastic report for San Diego. Calls +18582146584 (test mode if no key).
"""
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

# Add project root to path for imports (works with uv project)
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "apps" / "voice-alerts" / "src"))

try:
    from snaptrash_voice_alerts.trigger import run_voice_alert_check
    from snaptrash_voice_alerts.services.vapi_client import vapi_client
    from snaptrash_common.schemas import PlasticReportContext
    print("✅ Using full voice-alerts package")
    FULL_MODE = True
except ImportError as e:
    print(f"⚠️ Package import failed ({e}). Using direct minimal call.")
    from snaptrash_common.schemas import PlasticReportContext
    from snaptrash_voice_alerts.services.vapi_client import vapi_client
    FULL_MODE = False


def create_sample_report() -> 'PlasticReportContext':
    """Sample report for testing (avoids full DB query)."""
    return PlasticReportContext(
        locality="92101",
        neighborhood="Downtown San Diego",
        total_plastic_kg=187.5,
        harmful_count=12,
        pet_kg=95.2,
        weekly_plastic_count=45,
        active_restaurants=8,
        threshold=150.0,
        lab_recommendation="Contact BluumBio in Berkeley, CA immediately for enzyme deployment.",
        stats_summary="Locality plastic waste: 187.5kg this week (12 harmful items, 95kg PET). Exceeds 150kg threshold by 25%. 8 restaurants impacted.",
        forecast_note="Prophet forecast: Rising to 220kg next week without action.",
        action_call="Urgent: Switch to compostables and alert suppliers."
    )


def main():
    print(f"\n=== SnapTrash Voice Alert Caller === {datetime.now(timezone.utc)}")
    print("This script automatically triggers a Vapi call with plastic waste report.")

    if FULL_MODE:
        # Prefer full trigger (queries DB if available)
        try:
            run_voice_alert_check("92101")  # Specific ZIP for demo
            print("\n✅ Full trigger completed. Check voice_alerts table and Vapi dashboard.")
            return
        except Exception as e:
            print(f"Full trigger fallback due to: {e}. Using direct call...")

    # Minimal direct call (works without full DB)
    report = create_sample_report()
    print(f"Sample report for {report.neighborhood}: {report.total_plastic_kg}kg plastic (>150 threshold)")

    call_id = vapi_client.initiate_call(report)
    if call_id:
        print(f"Call initiated (ID: {call_id}). Polling for transcript...")
        result = vapi_client.poll_call(call_id, max_polls=8, poll_interval=3)
        print(f"Call status: {result.get('status')}")
        print(f"Transcript preview: {result.get('transcript', 'N/A')[:150]}...")
        print("\n✅ Call completed. View full details in Vapi dashboard (https://dashboard.vapi.ai/calls) or voice_alerts table.")
    else:
        print("\n⚠️ Call skipped (test mode or config). Add VAPI_API_KEY to .env for live calls.")
        print("Test mode logged sample alert. Update Vapi Assistant prompt with report variables.")

    print("\nNext steps:")
    print("1. Ensure VAPI_API_KEY in .env")
    print("2. Run `uv run --project apps/analytics python scripts/bootstrap_databricks.py` (if table missing)")
    print("3. Customize Vapi Assistant prompt in dashboard.vapi.ai")
    print("4. For production: Schedule via Databricks job or cron.")


if __name__ == "__main__":
    main()
