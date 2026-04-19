"""
VapiClient for initiating voice alerts and polling results.
Adapted from VAPI_TWILIO_VOICE_CALLING_INTEGRATION.md (PriceWar/Rex implementation).
Uses httpx for API calls to https://api.vapi.ai. Passes PlasticReportContext
via assistantOverrides.variableValues for Liquid templating in Vapi Assistant prompt.
Handles polling, transcripts, errors (SIP faults, rate limits, toll-free).
"""
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

import httpx
from snaptrash_common.env import settings
from snaptrash_common.schemas import PlasticReportContext, VoiceAlertRow
from snaptrash_common.tables import VOICE_ALERTS
from snaptrash_common.databricks_client import execute, fetch_all  # for logging


class VapiClient:
    """Client for Vapi.ai voice calls with context injection and polling."""

    def __init__(self):
        self.api_key = settings.VAPI_API_KEY
        self.assistant_id = settings.VAPI_ASSISTANT_ID
        self.phone_number_id = settings.VAPI_PHONE_NUMBER_ID
        self.default_phone = settings.DEFAULT_ALERT_PHONE
        self.test_override = settings.TEST_PHONE_OVERRIDE
        self.base_url = "https://api.vapi.ai"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        self._validate_config()

    def _validate_config(self) -> None:
        """Ensure config is valid (per VAPI guide). Soft validation for import/test."""
        self.configured = bool(
            self.api_key
            and len(self.api_key) > 10
            and not self.api_key.startswith(("your-", "sk-test", "YOUR_"))
            and self.api_key not in ("", "none", "null")
        )
        if not self.configured:
            print("⚠️ VAPI_API_KEY invalid/missing. Calls will skip to test mode (set in .env with your existing key).")
        if not self.assistant_id or not self.phone_number_id:
            print("Warning: VAPI_ASSISTANT_ID or PHONE_NUMBER_ID not set. Use TEST_PHONE_OVERRIDE.")
        if self.configured:
            print(f"VapiClient initialized with Assistant: {self.assistant_id[:10]}..., Phone ID: {self.phone_number_id[:10]}...")
        else:
            print("VapiClient in test mode.")

    def _sanitize_variable_values(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize for Vapi variableValues (dicts->JSON, None->'', per guide)."""
        sanitized = {}
        for k, v in data.items():
            if v is None:
                sanitized[k] = ""
            elif isinstance(v, (dict, list)):
                sanitized[k] = json.dumps(v, default=str)
            else:
                sanitized[k] = str(v)
        return sanitized

    def _normalize_phone(self, phone: str) -> str:
        """Ensure E.164 format. Use test override if set (per VAPI guide)."""
        if self.test_override and self.test_override.strip():
            return self.test_override.strip()
        if not phone.startswith("+"):
            phone = "+" + phone.lstrip("0")
        # Avoid toll-free per guide (would cause SIP 403)
        if any(phone.startswith(prefix) for prefix in ["+1 8", "+1800", "+1888", "+1877", "+1866", "+1855"]):
            print("Warning: Toll-free number detected; may fail with SIP 403.")
        return phone

    def initiate_call(self, report: PlasticReportContext, target_phone: str | None = None) -> str | None:
        """Initiate Vapi call with plastic report context. Returns call_id or None."""
        phone = self._normalize_phone(target_phone or self.default_phone)
        # Create alert row first
        alert_id = str(uuid.uuid4())
        context_dict = report.model_dump()
        context_json = json.dumps(context_dict)

        # Log to Databricks immediately
        now = datetime.now(timezone.utc).isoformat()
        execute(
            f"""
            INSERT INTO {VOICE_ALERTS} (alert_id, zip, neighborhood, triggered_at,
                plastic_volume_7day, threshold, report_context_json, status, notified)
            VALUES (:id, :zip, :nb, :ts, :vol, :thr, :ctx, 'triggered', false)
            """,
            {
                "id": alert_id,
                "zip": report.locality,  # reuse zip field for locality
                "nb": report.neighborhood,
                "ts": now,
                "vol": report.total_plastic_kg,
                "thr": report.threshold,
                "ctx": context_json,
            },
        )
        print(f"✅ Logged voice alert {alert_id} for {report.neighborhood} ({report.total_plastic_kg:.1f}kg plastic)")

        if not self.configured or not self.assistant_id or not self.phone_number_id:
            print("⚠️ No Vapi config - skipping actual call (test mode). Logged to DB only.")
            execute(f"UPDATE {VOICE_ALERTS} SET status = 'skipped' WHERE alert_id = :id", {"id": alert_id})
            return None

        payload = {
            "assistantId": self.assistant_id,
            "phoneNumberId": self.phone_number_id,
            "customer": {"number": phone},
            "assistantOverrides": {
                "variableValues": self._sanitize_variable_values(context_dict),
            },
        }

        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(
                    f"{self.base_url}/call",
                    headers=self.headers,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
                call_id = data.get("id")
                if call_id:
                    print(f"✅ Call initiated: {call_id} to {phone[-4:]} (report for {report.neighborhood})")
                    # Update with call_id
                    execute(
                        f"UPDATE {VOICE_ALERTS} SET call_id = :cid, status = 'calling' WHERE alert_id = :id",
                        {"cid": call_id, "id": alert_id},
                    )
                    return call_id
                return None
        except httpx.HTTPError as e:
            print(f"❌ Vapi initiate failed: {e}")
            execute(
                f"UPDATE {VOICE_ALERTS} SET status = 'failed', ended_reason = :reason WHERE alert_id = :id",
                {"reason": str(e)[:200], "id": alert_id},
            )
            return None

    def poll_call(self, call_id: str, max_polls: int = 60, poll_interval: int = 5) -> Dict[str, Any]:
        """Poll for call status and transcript (per VAPI guide: handle 429, ended states)."""
        terminal_statuses = {"ended", "not-found", "deletion-failed", "error"}
        transcript = ""
        ended_reason = None

        for i in range(max_polls):
            try:
                with httpx.Client(timeout=10.0) as client:
                    resp = client.get(
                        f"{self.base_url}/call/{call_id}",
                        headers=self.headers,
                    )
                    if resp.status_code == 429:
                        retry_after = int(resp.headers.get("Retry-After", 10))
                        print(f"Rate limited, sleeping {retry_after}s")
                        time.sleep(retry_after)
                        continue
                    resp.raise_for_status()
                    data = resp.json()

                    status = data.get("status", "")
                    ended_reason = data.get("endedReason") or data.get("ended_reason")
                    # Extract transcript (multiple possible locations per guide)
                    if "transcript" in data:
                        transcript = data["transcript"]
                    elif data.get("artifact", {}).get("transcript"):
                        transcript = data["artifact"]["transcript"]
                    elif "messages" in data:
                        messages = data["messages"]
                        transcript = "\n".join([f"{m.get('role','')}: {m.get('content','')}" for m in messages if m.get("content")])

                    print(f"Poll {i+1}/{max_polls}: status={status}, ended={bool(ended_reason)}")

                    if status in terminal_statuses or ended_reason:
                        print(f"Call ended: {ended_reason}. Transcript length: {len(transcript)}")
                        break

                    time.sleep(poll_interval)
            except Exception as e:
                print(f"Poll error: {e}")
                time.sleep(poll_interval * 2)

        return {
            "call_id": call_id,
            "transcript": transcript.strip(),
            "ended_reason": ended_reason or "unknown",
            "status": "completed" if transcript else "failed",
        }

    def record_call_outcome(self, alert_id: str, poll_result: Dict[str, Any]) -> None:
        """Update Databricks with final transcript and status."""
        execute(
            f"""
            UPDATE {VOICE_ALERTS}
            SET transcript = :trans, status = :status, ended_reason = :reason, notified = true
            WHERE alert_id = :id
            """,
            {
                "trans": poll_result["transcript"][:5000],  # truncate if too long
                "status": poll_result["status"],
                "reason": poll_result["ended_reason"],
                "id": alert_id,
            },
        )
        print(f"✅ Recorded outcome for alert {alert_id}: {poll_result['status']}")


# Singleton
vapi_client = VapiClient()
