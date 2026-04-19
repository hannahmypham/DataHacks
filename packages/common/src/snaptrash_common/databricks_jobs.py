"""
Shared Databricks Jobs API helpers.

Used by both:
  - apps/ingestion/services/pipeline_trigger.py  (FastAPI, runs in-process with cooldown)
  - infrastructure/lambda-detector/handler.py    (AWS Lambda, stateless, no cooldown needed)

Single implementation here avoids drift between the two callers.
"""
from __future__ import annotations

import json
import urllib.request

from .env import settings


def submit_aggregation_job(run_name: str = "snaptrash-agg-trigger") -> str | None:
    """Submit the 02_aggregations notebook as a one-time Databricks job run.

    Returns the run_id string on success, None on failure.
    Errors are logged but never re-raised — callers should treat this as
    fire-and-forget (scan data is already committed to Delta).
    """
    host = (settings.DATABRICKS_HOST or "").rstrip("/")
    token = settings.DATABRICKS_TOKEN
    user = settings.DATABRICKS_USER

    if not host or not token or not user:
        print("  [submit_aggregation_job] DATABRICKS_HOST/TOKEN/USER not set — skipping trigger.")
        return None

    nb_path = f"/Users/{user}/snaptrash/02_aggregations"
    body = json.dumps(
        {
            "run_name": run_name,
            "tasks": [
                {
                    "task_key": "02_aggregations",
                    "notebook_task": {
                        "notebook_path": nb_path,
                        "source": "WORKSPACE",
                    },
                }
            ],
        }
    ).encode()

    req = urllib.request.Request(
        f"{host}/api/2.2/jobs/runs/submit",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            resp = json.loads(r.read())
            run_id = str(resp.get("run_id", ""))
            print(f"  [submit_aggregation_job] run_id={run_id}")
            return run_id
    except Exception as e:
        print(f"  [submit_aggregation_job] failed ({e}) — insights will update on next schedule.")
        return None
