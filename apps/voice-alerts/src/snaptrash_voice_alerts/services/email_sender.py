"""
SMTP email sender for plastic waste threshold alerts.
Adapted from EMAIL_CONFIRMATION_SYSTEM.md (pure stdlib smtplib, MIMEMultipart for HTML+plain).
Sends rich report with stats from PlasticReportContext to hardcoded emails (manasvinsurya.nitt02@gmail.com + mbj@ucsd.edu).
No external deps. Logs via logger; DB logging handled in trigger.
"""
from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List

from snaptrash_common.env import settings
from snaptrash_common.schemas import PlasticReportContext

logger = logging.getLogger("email_sender")


def send_plastic_alert_email(
    report: PlasticReportContext, to_emails: List[str] | None = None
) -> bool:
    """Send HTML email report for high plastic waste alert.

    Uses Gmail SMTP (STARTTLS). Follows EMAIL_CONFIRMATION_SYSTEM.md patterns
    for auth error handling and Gmail-friendly HTML (inline styles, tables).
    Hardcodes lab rec to mbj@ucsd.edu per user spec.
    """
    if not settings.SMTP_USER or not settings.SMTP_PASS:
        logger.warning("SMTP credentials not configured (SMTP_USER/SMTP_PASS). Skipping email send.")
        return False

    if to_emails is None:
        to_list = [e.strip() for e in settings.ALERT_TO_EMAILS.split(",") if e.strip()]
    else:
        to_list = to_emails

    if not to_list:
        logger.error("No recipient emails provided.")
        return False

    from_email = settings.ALERT_FROM_EMAIL or settings.SMTP_USER
    subject = f"🚨 SnapTrash Plastic Alert: {report.neighborhood} ({report.total_plastic_kg:.1f}kg > {report.threshold}kg threshold)"

    # Rich HTML report (Gmail-friendly table layout, no external images)
    html_content = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            h2 {{ color: #d32f2f; border-bottom: 2px solid #d32f2f; padding-bottom: 10px; }}
            table {{ border-collapse: collapse; width: 100%; margin: 15px 0; }}
            th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
            th {{ background-color: #f5f5f5; }}
            .highlight {{ background-color: #fff3e0; font-weight: bold; }}
            .footer {{ font-size: 0.85em; color: #666; margin-top: 20px; border-top: 1px solid #eee; padding-top: 10px; }}
        </style>
    </head>
    <body style="max-width: 650px; margin: 20px auto; padding: 20px; background-color: #f9f9f9;">
        <h2>SnapTrash High Plastic Waste Alert</h2>
        <p><strong>Locality:</strong> {report.neighborhood} (ZIP: {report.locality})</p>
        <p class="highlight"><strong>Alert Triggered:</strong> Weekly plastic volume {report.total_plastic_kg:.1f}kg exceeds threshold of {report.threshold}kg/week.</p>

        <h3>Key Statistics</h3>
        <table>
            <tr><th>Metric</th><th>Value</th></tr>
            <tr><td>Total Plastic Waste</td><td class="highlight">{report.total_plastic_kg:.1f} kg</td></tr>
            <tr><td>Harmful Plastics Detected</td><td>{report.harmful_count}</td></tr>
            <tr><td>PET Contribution</td><td>{report.pet_kg:.1f} kg</td></tr>
            <tr><td>Weekly Plastic Items</td><td>{report.weekly_plastic_count}</td></tr>
            <tr><td>Impacted Restaurants</td><td>{report.active_restaurants}</td></tr>
        </table>

        <p>Our report for this locality documents a high volume of plastic waste—approximately {report.total_plastic_kg:.1f} kilograms this week, consisting primarily of PET, polystyrene, and other harmful types. This level is going well beyond regulatory and environmental limits, adding substantially to landfills and long-term plastic pollution in the San Diego region.</p>

        <p>As the company producing plastic-eating enzymes, we are contacting you to request your help. Your innovative enzyme solutions could effectively break down this waste, reduce landfill contributions, and provide a scalable biological alternative for affected restaurants. Detailed scan data, trends, and resource lists from our analysis are available to support immediate collaboration on deployment.</p>

        <h3>Summary &amp; Forecast</h3>
        <p>{report.stats_summary}</p>
        <p>{report.forecast_note}</p>
        <p>{report.action_call or 'Immediate action recommended: Switch to compostables, audit suppliers, and deploy enzymes.'}</p>

        <div class="footer">
            <p>This is an automated alert from the SnapTrash platform (Databricks + Groq Vision pipeline).<br>
            Generated from recent scans in scans_unified view. See locality_agg for full aggregates.<br>
            To stop alerts, update notified flag in EMAIL_ALERTS table or adjust thresholds.</p>
            <p><small>Sent from: {from_email}</small></p>
        </div>
    </body>
    </html>
    """

    plain_content = f"""SnapTrash Plastic Waste Alert - {report.neighborhood}

Our report for this locality documents a high volume of plastic waste—approximately {report.total_plastic_kg:.1f} kilograms this week, consisting primarily of PET, polystyrene, and other harmful types. This level is going well beyond regulatory and environmental limits, adding substantially to landfills and long-term plastic pollution in the San Diego region.

As the company producing plastic-eating enzymes, we are contacting you to request your help. Your innovative enzyme solutions could effectively break down this waste, reduce landfill contributions, and provide a scalable biological alternative for affected restaurants. Detailed scan data, trends, and resource lists from our analysis are available to support immediate collaboration on deployment.

Summary: {report.stats_summary}
Forecast: {report.forecast_note}

This is an automated report from SnapTrash.
"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = ", ".join(to_list)

    msg.attach(MIMEText(plain_content, "plain"))
    msg.attach(MIMEText(html_content, "html"))

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASS)
            server.send_message(msg)
        logger.info(f"✅ Plastic alert email sent successfully to {to_list} for {report.neighborhood} ({report.total_plastic_kg:.1f}kg)")
        return True
    except smtplib.SMTPAuthenticationError as e:
        logger.error(
            "SMTP Authentication failed. Verify SMTP_USER=%s and SMTP_PASS is a valid Gmail App Password (not account password). "
            "See EMAIL_CONFIRMATION_SYSTEM.md for setup. Error: %s",
            settings.SMTP_USER,
            e,
        )
        return False
    except Exception as e:
        logger.error("Failed to send plastic alert email: %s", e)
        return False


def send_batch_alert_emails(reports: List[PlasticReportContext]) -> int:
    """Send emails for multiple reports. Returns count of successful sends."""
    success_count = 0
    for report in reports:
        if send_plastic_alert_email(report):
            success_count += 1
    return success_count
