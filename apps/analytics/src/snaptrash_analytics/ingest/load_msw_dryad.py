"""Download Dryad US Municipal Solid Waste CSV → snaptrash.msw_baseline.

Dataset: https://datadryad.org/dataset/doi:10.5061/dryad.bzkh189h4
DOI: 10.5061/dryad.bzkh189h4

Strategy:
1. Resolve dataset metadata via Dryad API.
2. Download all CSV files in dataset to data/dryad/.
3. Read with pandas, normalize to msw_baseline schema, write to Delta.
"""
from __future__ import annotations
import io
import urllib.parse
from pathlib import Path
import httpx
import pandas as pd

from snaptrash_common.databricks_client import execute
from snaptrash_common.tables import MSW_BASELINE
from snaptrash_common.env import REPO_ROOT

DOI = "doi:10.5061/dryad.bzkh189h4"
DRYAD_BASE = "https://datadryad.org/api/v2"
DATA_DIR = REPO_ROOT / "data" / "dryad"


def _doi_url() -> str:
    return f"{DRYAD_BASE}/datasets/{urllib.parse.quote(DOI, safe='')}"


def fetch_dataset_files() -> list[dict]:
    with httpx.Client(timeout=60) as c:
        ds = c.get(_doi_url()).raise_for_status().json()
        latest_version = ds["_links"]["stash:version"]["href"]
        files = c.get(f"{DRYAD_BASE}{latest_version}/files").raise_for_status().json()
        return files.get("_embedded", {}).get("stash:files", [])


def download_files() -> list[Path]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    files = fetch_dataset_files()
    with httpx.Client(timeout=300) as c:
        for f in files:
            name = f["path"]
            if not name.lower().endswith((".csv", ".xlsx")):
                continue
            href = f["_links"]["stash:download"]["href"]
            url = f"{DRYAD_BASE}{href}" if href.startswith("/") else href
            out = DATA_DIR / name
            print(f"↓ {name}")
            r = c.get(url)
            r.raise_for_status()
            out.write_bytes(r.content)
            paths.append(out)
    return paths


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Map Dryad columns → msw_baseline schema. Best-effort; tweak after inspecting CSV headers."""
    cols_lower = {c.lower(): c for c in df.columns}

    def pick(*names: str) -> str | None:
        for n in names:
            if n in cols_lower:
                return cols_lower[n]
        return None

    year_c = pick("year")
    state_c = pick("state", "state_name")
    type_c = pick("waste_type", "category", "material")
    tons_c = pick("total_tons", "tons", "tonnage")

    if not all([year_c, state_c, tons_c]):
        raise ValueError(f"Missing required columns. Found: {list(df.columns)[:20]}")

    out = pd.DataFrame({
        "year": pd.to_numeric(df[year_c], errors="coerce").astype("Int64"),
        "state": df[state_c].astype(str).str.strip(),
        "waste_type": df[type_c].astype(str).str.strip() if type_c else "all",
        "total_tons": pd.to_numeric(df[tons_c], errors="coerce"),
    }).dropna(subset=["year", "state", "total_tons"])

    # rough proxy: avg per restaurant ~ total tons * 0.15 commercial / 1000 establishments
    out["avg_commercial_waste_kg_per_restaurant"] = out["total_tons"] * 0.15 * 1000 / 1000
    return out


def to_values_clause(df: pd.DataFrame) -> str:
    rows = []
    for _, r in df.iterrows():
        state = str(r["state"]).replace("'", "''")
        wt = str(r["waste_type"]).replace("'", "''")
        rows.append(
            f"({int(r['year'])}, '{state}', '{wt}', {float(r['total_tons'])}, "
            f"{float(r['avg_commercial_waste_kg_per_restaurant'])})"
        )
    return ",\n".join(rows)


def load_to_delta(df: pd.DataFrame, *, replace: bool = True) -> int:
    if replace:
        execute(f"DELETE FROM {MSW_BASELINE}")
    BATCH = 500
    total = 0
    for i in range(0, len(df), BATCH):
        chunk = df.iloc[i : i + BATCH]
        execute(f"INSERT INTO {MSW_BASELINE} VALUES {to_values_clause(chunk)}")
        total += len(chunk)
        print(f"  → inserted {total}/{len(df)}")
    return total


def main():
    paths = download_files()
    if not paths:
        raise SystemExit("no CSV/XLSX files found in Dryad dataset")
    frames = []
    for p in paths:
        df = pd.read_excel(p) if p.suffix == ".xlsx" else pd.read_csv(p)
        frames.append(normalize(df))
    full = pd.concat(frames, ignore_index=True)
    print(f"normalized {len(full)} rows")
    n = load_to_delta(full)
    print(f"✅ loaded {n} rows into {MSW_BASELINE}")


if __name__ == "__main__":
    main()
