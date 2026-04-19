"""
One-shot pusher:
  1. Upload all pylib source under packages/common/src + apps/analytics/src
     to  /Volumes/workspace/analytics/pylib/<snaptrash_common|snaptrash_analytics>/...
     via Files API (PUT /api/2.0/fs/files/...).
  2. Upload notebooks to /Workspace/Users/<user>/snaptrash/ via Workspace Import API.
  3. Submit a one-off multi-task Job (runs/submit) that runs 01b → 02 → 03 in order
     on the workspace's serverless compute.
  4. Poll run status and print links.

Run:
  python scripts/push_to_databricks.py
"""
from __future__ import annotations
import base64
import json
import os
import pathlib
import sys
import time
import urllib.parse
import urllib.request

# --- load .env ---------------------------------------------------------------
ROOT = pathlib.Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
for line in ENV_PATH.read_text().splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, v = line.split("=", 1)
    os.environ.setdefault(k.strip(), v.strip())

HOST = os.environ["DATABRICKS_HOST"].rstrip("/")
TOKEN = os.environ["DATABRICKS_TOKEN"]
USER_EMAIL = os.environ.get("DATABRICKS_USER", "ara023@ucsd.edu")
WS_DIR = f"/Users/{USER_EMAIL}/snaptrash"


def _req(method: str, path: str, body: dict | bytes | None = None,
         headers: dict | None = None) -> dict:
    url = f"{HOST}{path}"
    h = {"Authorization": f"Bearer {TOKEN}"}
    if headers:
        h.update(headers)
    if isinstance(body, (dict, list)):
        data = json.dumps(body).encode()
        h.setdefault("Content-Type", "application/json")
    elif isinstance(body, (bytes, bytearray)):
        data = bytes(body)
    else:
        data = None
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.request.HTTPError as e:
        msg = e.read().decode(errors="ignore")
        raise RuntimeError(f"{method} {path} -> {e.code}: {msg}") from None


# -----------------------------------------------------------------------------
# 1. Upload pylib source to Unity Catalog Volume
# -----------------------------------------------------------------------------
PYLIB_VOL = "/Volumes/workspace/analytics/pylib"

PYLIB_ROOTS = [
    (ROOT / "packages/common/src/snaptrash_common", "snaptrash_common"),
    (ROOT / "apps/analytics/src/snaptrash_analytics", "snaptrash_analytics"),
]


def upload_pylib() -> None:
    print("→ uploading pylib source to Volume …")
    for local_root, pkg_name in PYLIB_ROOTS:
        for p in sorted(local_root.rglob("*.py")):
            if "__pycache__" in p.parts:
                continue
            rel = p.relative_to(local_root).as_posix()
            vol_path = f"{PYLIB_VOL}/{pkg_name}/{rel}"
            api_path = "/api/2.0/fs/files" + urllib.parse.quote(vol_path)
            body = p.read_bytes()
            # Files API PUT; include ?overwrite=true
            _req("PUT", api_path + "?overwrite=true", body,
                 headers={"Content-Type": "application/octet-stream"})
            print(f"   {vol_path}")


# -----------------------------------------------------------------------------
# 2. Upload notebooks to Workspace
# -----------------------------------------------------------------------------
NOTEBOOKS = [
    ("01b_load_gold_tables.py", "01b_load_gold_tables"),
    ("02_aggregations.py",      "02_aggregations"),
    ("03_prophet_forecast.py",  "03_prophet_forecast"),
]

def ensure_ws_dir() -> None:
    _req("POST", "/api/2.0/workspace/mkdirs", {"path": WS_DIR})


def upload_notebooks() -> list[str]:
    print("→ uploading notebooks to Workspace …")
    ensure_ws_dir()
    paths: list[str] = []
    for fname, stem in NOTEBOOKS:
        local = ROOT / "apps/analytics/notebooks" / fname
        ws_path = f"{WS_DIR}/{stem}"
        content = base64.b64encode(local.read_bytes()).decode()
        _req("POST", "/api/2.0/workspace/import", {
            "path": ws_path,
            "format": "SOURCE",
            "language": "PYTHON",
            "content": content,
            "overwrite": True,
        })
        paths.append(ws_path)
        print(f"   {ws_path}")
    return paths


# -----------------------------------------------------------------------------
# 3. Submit one-off multi-task job
# -----------------------------------------------------------------------------
def submit_run(nb_paths: list[str]) -> int:
    print("→ submitting multi-task run …")
    tasks = []
    prev: str | None = None
    for ws_path in nb_paths:
        key = ws_path.rsplit("/", 1)[-1].replace(".", "_")
        t = {
            "task_key": key,
            "notebook_task": {"notebook_path": ws_path, "source": "WORKSPACE"},
        }
        if prev:
            t["depends_on"] = [{"task_key": prev}]
        tasks.append(t)
        prev = key
    body = {
        "run_name": f"snaptrash-analytics-pipeline-{int(time.time())}",
        "tasks": tasks,
    }
    resp = _req("POST", "/api/2.2/jobs/runs/submit", body)
    run_id = resp["run_id"]
    print(f"   run_id={run_id}   {HOST}/#job/run/{run_id}")
    return run_id


def poll(run_id: int) -> dict:
    print("→ polling …")
    while True:
        r = _req("GET", f"/api/2.2/jobs/runs/get?run_id={run_id}")
        state = r.get("state", {})
        life = state.get("life_cycle_state")
        result = state.get("result_state")
        print(f"   life_cycle={life}  result={result}")
        if life in ("TERMINATED", "INTERNAL_ERROR", "SKIPPED"):
            return r
        time.sleep(15)


# -----------------------------------------------------------------------------
def main() -> None:
    upload_pylib()
    nb_paths = upload_notebooks()
    run_id = submit_run(nb_paths)
    final = poll(run_id)
    print(json.dumps(final.get("state", {}), indent=2))
    # per-task result
    for t in final.get("tasks", []):
        s = t.get("state", {})
        print(f"   {t['task_key']:35s} {s.get('life_cycle_state')}/{s.get('result_state')}")
    if final.get("state", {}).get("result_state") != "SUCCESS":
        sys.exit(1)


if __name__ == "__main__":
    main()
