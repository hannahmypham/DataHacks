"""Fire-and-forget Databricks pipeline trigger.

Called after each successful scan write. A 90-second cooldown prevents
overlapping runs when multiple photos are submitted in quick succession.
"""
from __future__ import annotations
import base64, json, logging, os, pathlib, threading, time, urllib.parse, urllib.request

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_last_triggered: float = 0.0
_COOLDOWN = 90.0  # seconds

ROOT = pathlib.Path(__file__).resolve().parents[5]  # DataHacks/


def _req(host: str, token: str, method: str, path: str, body=None):
    url = f"{host}{path}"
    headers = {"Authorization": f"Bearer {token}"}
    data = None
    if isinstance(body, (dict, list)):
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
        return json.loads(raw) if raw else {}


def _run(host: str, token: str, databricks_user: str):
    ws = f"/Users/{databricks_user}/snaptrash"
    notebooks = [
        (f"{ws}/02_aggregations", None),
        (f"{ws}/03_prophet_forecast", "02_aggregations"),
    ]
    tasks = []
    for nb_path, depends_on in notebooks:
        key = nb_path.rsplit("/", 1)[-1]
        t = {"task_key": key, "notebook_task": {"notebook_path": nb_path, "source": "WORKSPACE"}}
        if depends_on:
            t["depends_on"] = [{"task_key": depends_on}]
        tasks.append(t)

    r = _req(host, token, "POST", "/api/2.2/jobs/runs/submit", {
        "run_name": f"snaptrash-auto-{int(time.time())}",
        "tasks": tasks,
    })
    run_id = r.get("run_id")
    logger.info(f"[pipeline_trigger] Databricks run submitted run_id={run_id}")
    return run_id


def trigger():
    """Submit pipeline in a background thread with cooldown guard."""
    global _last_triggered

    host = os.environ.get("DATABRICKS_HOST", "").rstrip("/")
    token = os.environ.get("DATABRICKS_TOKEN", "")
    user = os.environ.get("DATABRICKS_USER", "ara023@ucsd.edu")

    if not host or not token:
        logger.warning("[pipeline_trigger] DATABRICKS_HOST/TOKEN not set — skipping auto-trigger")
        return

    with _lock:
        now = time.monotonic()
        if now - _last_triggered < _COOLDOWN:
            remaining = int(_COOLDOWN - (now - _last_triggered))
            logger.info(f"[pipeline_trigger] cooldown active ({remaining}s left) — skipping")
            return
        _last_triggered = now

    def _bg():
        try:
            _run(host, token, user)
        except Exception as e:
            logger.error(f"[pipeline_trigger] failed to submit run: {e}")

    threading.Thread(target=_bg, daemon=True).start()
