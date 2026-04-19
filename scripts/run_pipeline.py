"""
Quick runner: upload pylib → run 02_aggregations → 03_prophet_forecast.
Skips 01b (gold tables already loaded).

Usage:
  python scripts/run_pipeline.py
"""
from __future__ import annotations
import base64, json, os, pathlib, sys, time, urllib.parse, urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
for line in (ROOT / ".env").read_text().splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, v = line.split("=", 1)
    os.environ.setdefault(k.strip(), v.strip())

HOST  = os.environ["DATABRICKS_HOST"].rstrip("/")
TOKEN = os.environ["DATABRICKS_TOKEN"]
USER  = os.environ.get("DATABRICKS_USER", "ara023@ucsd.edu")
WS    = f"/Users/{USER}/snaptrash"


def _req(method, path, body=None, headers=None):
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


# 1. Upload pylib
PYLIB_VOL = "/Volumes/workspace/analytics/pylib"
PYLIB_ROOTS = [
    (ROOT / "packages/common/src/snaptrash_common",   "snaptrash_common"),
    (ROOT / "apps/analytics/src/snaptrash_analytics", "snaptrash_analytics"),
]

def upload_pylib():
    print("→ uploading pylib …")
    count = 0
    for local_root, pkg in PYLIB_ROOTS:
        for p in sorted(local_root.rglob("*.py")):
            if "__pycache__" in p.parts:
                continue
            rel = p.relative_to(local_root).as_posix()
            vol = f"{PYLIB_VOL}/{pkg}/{rel}"
            api = "/api/2.0/fs/files" + urllib.parse.quote(vol)
            _req("PUT", api + "?overwrite=true", p.read_bytes(),
                 headers={"Content-Type": "application/octet-stream"})
            count += 1
    print(f"   {count} files uploaded")


# 2. Upload & run 02→03
NOTEBOOKS = [
    ("02_aggregations.py",   "02_aggregations"),
    ("03_prophet_forecast.py", "03_prophet_forecast"),
]

def upload_notebooks():
    print("→ uploading notebooks …")
    _req("POST", "/api/2.0/workspace/mkdirs", {"path": WS})
    paths = []
    for fname, stem in NOTEBOOKS:
        local = ROOT / "apps/analytics/notebooks" / fname
        ws_path = f"{WS}/{stem}"
        _req("POST", "/api/2.0/workspace/import", {
            "path": ws_path, "format": "SOURCE", "language": "PYTHON",
            "content": base64.b64encode(local.read_bytes()).decode(),
            "overwrite": True,
        })
        paths.append(ws_path)
        print(f"   {ws_path}")
    return paths


def submit(nb_paths):
    print("→ submitting run …")
    tasks, prev = [], None
    for p in nb_paths:
        key = p.rsplit("/", 1)[-1]
        t = {"task_key": key, "notebook_task": {"notebook_path": p, "source": "WORKSPACE"}}
        if prev:
            t["depends_on"] = [{"task_key": prev}]
        tasks.append(t); prev = key
    r = _req("POST", "/api/2.2/jobs/runs/submit", {
        "run_name": f"snaptrash-agg-{int(time.time())}",
        "tasks": tasks,
    })
    run_id = r["run_id"]
    print(f"   run_id={run_id}  {HOST}/#job/run/{run_id}")
    return run_id


def poll(run_id):
    print("→ polling …")
    while True:
        r = _req("GET", f"/api/2.2/jobs/runs/get?run_id={run_id}")
        s = r.get("state", {})
        lc, rs = s.get("life_cycle_state"), s.get("result_state")
        print(f"   {lc}/{rs}")
        if lc in ("TERMINATED", "INTERNAL_ERROR", "SKIPPED"):
            for t in r.get("tasks", []):
                ts = t.get("state", {})
                print(f"   {t['task_key']:35s} {ts.get('life_cycle_state')}/{ts.get('result_state')}")
            return r
        time.sleep(15)


def check_results():
    from snaptrash_common.databricks_client import fetch_all
    sys.path.insert(0, str(ROOT / "packages/common/src"))
    print("\n=== RESULTS ===")
    try:
        n = fetch_all("SELECT COUNT(*) AS n FROM workspace.snaptrash.insights "
                      "WHERE computed_at >= NOW() - INTERVAL 1 HOUR")
        print(f"insights (last 1h): {n[0]['n']}")
        scored = fetch_all(
            "SELECT restaurant_id, zip, ROUND(sustainability_score,1) AS score, "
            "badge_tier, tier_emoji, ROUND(signal_1,1) s1, ROUND(signal_2,1) s2, "
            "ROUND(signal_3,1) s3, ROUND(signal_4,1) s4, ROUND(signal_5,1) s5 "
            "FROM workspace.snaptrash.insights "
            "WHERE computed_at >= NOW() - INTERVAL 1 HOUR "
            "ORDER BY sustainability_score DESC LIMIT 10"
        )
        for row in scored:
            print(f"  {row['restaurant_id'][:22]:22s} score={row['score']} {row['tier_emoji']} "
                  f"s1={row['s1']} s2={row['s2']} s3={row['s3']} s4={row['s4']} s5={row['s5']}")
        loc = fetch_all("SELECT COUNT(*) AS n FROM workspace.snaptrash.locality_agg "
                        "WHERE computed_at >= NOW() - INTERVAL 1 HOUR")
        print(f"locality_agg (last 1h): {loc[0]['n']}")
        fc = fetch_all("SELECT COUNT(*) AS n FROM workspace.snaptrash.insights "
                       "WHERE forecast_food_kg > 0")
        print(f"insights with forecasts: {fc[0]['n']}")
    except Exception as e:
        print(f"  check_results error: {e}")


def main():
    upload_pylib()
    nb_paths = upload_notebooks()
    run_id = submit(nb_paths)
    final = poll(run_id)
    if final.get("state", {}).get("result_state") != "SUCCESS":
        print("❌ pipeline FAILED")
        sys.exit(1)
    print("✅ pipeline SUCCESS")


if __name__ == "__main__":
    main()
