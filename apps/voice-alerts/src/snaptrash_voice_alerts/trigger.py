"""
Trigger for voice + email alerts. Runs check for plastic >150kg/week (locality and restaurant),
generates reports using PlasticReportContext, triggers Vapi calls + SMTP emails to
hardcoded addresses (manasvinsurya.nitt02@gmail.com, mbj@ucsd.edu).
Uses email_sender.py (SMTP per EMAIL_CONFIRMATION_SYSTEM.md) and logs to DB.
Per snaptrash skill and plan. Repeated runs supported for demo (no duplicate check).
"""
import sys
from datetime import datetime, timezone
from typing import List

from snaptrash_common.env import settings
from .report import (
    generate_plastic_report,
    generate_restaurant_plastic_reports,
)
from .services.email_sender import send_batch_alert_emails
from .services.vapi_client import vapi_client


def run_voice_alert_check(specific_zip: str | None = None) -> None:
    """Main entrypoint for voice + email alerts (updated per plan).
    Checks localities (>150kg/wk) and individual restaurants (>30kg/wk).
    Sends one email (to enzyme company at mbj@ucsd.edu) with report on plastic volume/types exceeding limits and request for enzymes + Vapi calls. Logs to DB.
    Repeated runs supported for demo purposes (sample fallback always triggers).
    """
    now = datetime.now(timezone.utc)
    print(f"[{now}] Running SnapTrash Alert Check (voice + email; thresholds 150kg locality / 30kg restaurant)")

    print(f"Target phone: {settings.DEFAULT_ALERT_PHONE} (override: {settings.TEST_PHONE_OVERRIDE or 'none'})")
    if not settings.VAPI_API_KEY or len(settings.VAPI_API_KEY) <= 10:
        print("⚠️ VAPI_API_KEY not configured. Set in .env and provide your existing values.")

    locality_reports = generate_plastic_report(specific_zip)
    reports = locality_reports or generate_restaurant_plastic_reports(threshold=30.0)

    if not reports:
        print("✅ No localities or restaurants exceeding plastic thresholds. No alerts triggered.")
        return

    # Send emails first (SMTP, hardcoded recipients) — limited to one email per run for demo
    email_count = send_batch_alert_emails(reports[:1])
    print(f"📧 Sent {email_count} email alert to {settings.ALERT_TO_EMAILS}.")

    for report in reports:
        print(f"\nProcessing alert for {report.neighborhood} ({report.total_plastic_kg:.1f}kg plastic)...")
        call_id = vapi_client.initiate_call(report)
        if call_id:
            print("Polling for call completion...")
            poll_result = vapi_client.poll_call(call_id, max_polls=12, poll_interval=5)
            print(f"Call result: {poll_result.get('status', 'N/A')}. Transcript snippet: {poll_result.get('transcript', '')[:100] if poll_result.get('transcript') else 'N/A'}")
            print("✅ Voice alert processed.")
        else:
            print("Skipped call (test mode or error).")

    print("Alert check complete (voice + email). Check voice_alerts / EMAIL_ALERTS tables for logs.")


if __name__ == "__main__":
    run_voice_alert_check()
    # Example: run_voice_alert_check("92101") for specific ZIP
