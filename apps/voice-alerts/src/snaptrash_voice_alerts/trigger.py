"""
Trigger for voice + email alerts.
- Locality threshold: >150 kg/week plastic → Vapi call + SMTP email
- Restaurant threshold: >30 kg/week plastic → Vapi call + SMTP email
- Email dedup: skips send if EMAIL_ALERTS has a notified=true row for the
  same ZIP within the last 7 days.
- Transcript write-back: records poll outcome to VOICE_ALERTS.transcript.
"""
import json
import sys
import uuid
from datetime import datetime, timezone

from snaptrash_common.databricks_client import execute, fetch_all
from snaptrash_common.env import settings
from snaptrash_common.schemas import EmailAlertRow
from snaptrash_common.tables import EMAIL_ALERTS

from .report import (
    generate_plastic_report,
    generate_restaurant_plastic_reports,
)
from .services.email_sender import send_plastic_alert_email
from .services.vapi_client import vapi_client

# ── thresholds (also appear in report.py SQL — keep in sync) ─────────────────
LOCALITY_THRESHOLD_KG = 150.0   # CA plastic disposal avg: ~130kg/restaurant/wk (EPA 2022)
RESTAURANT_THRESHOLD_KG = 30.0  # per-restaurant share: ~20% of locality avg


def _already_emailed(zip_code: str, days: int = 7) -> bool:
    """Return True if EMAIL_ALERTS has a notified=true entry for this ZIP in last {days} days."""
    try:
        rows = fetch_all(
            f"""
            SELECT alert_id FROM {EMAIL_ALERTS}
            WHERE zip = :zip
              AND notified = true
              AND triggered_at >= CURRENT_TIMESTAMP - INTERVAL {days} DAYS
            LIMIT 1
            """,
            {"zip": zip_code},
        )
        return len(rows) > 0
    except Exception as e:
        print(f"  [dedup check failed: {e}] — allowing send")
        return False


def _log_email_alert(
    report,
    *,
    zip_code: str,
    sent_to: str,
    status: str,
    error: str | None = None,
) -> None:
    """Write result row to EMAIL_ALERTS table."""
    try:
        row = EmailAlertRow(
            alert_id=str(uuid.uuid4()),
            zip=zip_code,
            neighborhood=report.neighborhood,
            triggered_at=datetime.now(timezone.utc),
            plastic_volume_7day=report.total_plastic_kg,
            threshold=report.threshold,
            report_context_json=json.dumps(report.model_dump()),
            sent_to=sent_to,
            status=status,
            notified=(status == "sent"),
            error=error,
        )
        execute(
            f"""
            INSERT INTO {EMAIL_ALERTS}
              (alert_id, zip, neighborhood, triggered_at, plastic_volume_7day,
               threshold, report_context_json, sent_to, status, notified, error)
            VALUES (:id, :zip, :nb, :ts, :vol, :thr, :ctx, :to, :st, :notified, :err)
            """,
            {
                "id": row.alert_id,
                "zip": row.zip,
                "nb": row.neighborhood,
                "ts": row.triggered_at.isoformat(),
                "vol": row.plastic_volume_7day,
                "thr": row.threshold,
                "ctx": row.report_context_json,
                "to": row.sent_to,
                "st": row.status,
                "notified": row.notified,
                "err": row.error,
            },
        )
    except Exception as e:
        print(f"  [email_alert log failed: {e}]")


def run_voice_alert_check(specific_zip: str | None = None) -> None:
    """Main entrypoint for voice + email alerts.

    Checks localities (>150kg/wk) then individual restaurants (>30kg/wk).
    Each ZIP gets at most one email per 7 days (dedup via EMAIL_ALERTS).
    Each alert gets a Vapi call; transcript is written back to VOICE_ALERTS.
    """
    now = datetime.now(timezone.utc)
    print(f"[{now}] SnapTrash Alert Check — locality>{LOCALITY_THRESHOLD_KG}kg / restaurant>{RESTAURANT_THRESHOLD_KG}kg")

    if not settings.VAPI_API_KEY or len(settings.VAPI_API_KEY) <= 10:
        print("⚠️  VAPI_API_KEY not set — calls will log to DB only (test mode).")
    if not settings.ALERT_TO_EMAILS:
        print("⚠️  ALERT_TO_EMAILS not set — email sends will be skipped.")

    locality_reports = generate_plastic_report(specific_zip)
    reports = locality_reports or generate_restaurant_plastic_reports(threshold=RESTAURANT_THRESHOLD_KG)

    if not reports:
        print("✅ No localities/restaurants above threshold. No alerts needed.")
        return

    to_emails = [e.strip() for e in settings.ALERT_TO_EMAILS.split(",") if e.strip()]
    sent_to_str = ", ".join(to_emails)

    for report in reports:
        zip_code = report.locality
        print(f"\n── {report.neighborhood} ({report.total_plastic_kg:.1f}kg) ──")

        # ── Email (with dedup) ────────────────────────────────────────────
        if _already_emailed(zip_code):
            print(f"  Email skipped — already notified ZIP {zip_code} within 7 days.")
        elif not to_emails:
            print("  Email skipped — ALERT_TO_EMAILS not configured.")
        else:
            ok = send_plastic_alert_email(report, to_emails=to_emails)
            status = "sent" if ok else "failed"
            _log_email_alert(report, zip_code=zip_code, sent_to=sent_to_str, status=status)
            print(f"  Email → {sent_to_str}: {status}")

        # ── Voice call ───────────────────────────────────────────────────
        call_id, alert_id = vapi_client.initiate_call(report)
        if call_id:
            print("  Polling call completion...")
            poll_result = vapi_client.poll_call(call_id, max_polls=12, poll_interval=5)
            vapi_client.record_call_outcome(alert_id, poll_result)
            snippet = (poll_result.get("transcript") or "")[:120]
            print(f"  Call {poll_result.get('status')} — transcript: {snippet or '(empty)'}")
        else:
            print(f"  Call skipped (test mode) — alert_id={alert_id} logged.")

    print("\nAlert check complete. Rows written to VOICE_ALERTS + EMAIL_ALERTS.")


if __name__ == "__main__":
    run_voice_alert_check()
