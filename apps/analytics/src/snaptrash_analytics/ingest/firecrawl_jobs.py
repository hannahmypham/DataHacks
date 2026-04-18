"""Hour-1 scrape jobs — outputs JSON to data/.

Run once at hackathon start. Outputs consumed by:
- data/epa_banned.json    → ingestion plastic_analysis.py
- data/compost_facilities.json → analytics aggregations
- data/labs.json          → integration phase (SendGrid matching)
"""
from __future__ import annotations
import json
from pathlib import Path
from firecrawl import FirecrawlApp
from snaptrash_common import settings
from snaptrash_common.env import REPO_ROOT

OUT = REPO_ROOT / "data"


def app() -> FirecrawlApp:
    if not settings.FIRECRAWL_API_KEY:
        raise RuntimeError("FIRECRAWL_API_KEY missing in .env")
    return FirecrawlApp(api_key=settings.FIRECRAWL_API_KEY)


def scrape_epa_banned_plastics() -> dict:
    fc = app()
    res = fc.scrape_url(
        "https://www.epa.gov/trash-free-waters/plastic-bans",
        params={"formats": ["markdown", "json"]},
    )
    return res


def scrape_biocycle_compost() -> list[dict]:
    fc = app()
    res = fc.crawl_url(
        "https://www.biocycle.net/compost-facility-directory/",
        params={"limit": 200, "scrapeOptions": {"formats": ["markdown"]}},
    )
    return res.get("data", [])


def scrape_enzyme_labs() -> list[dict]:
    fc = app()
    seeds = [
        "https://www.carbios.com",
        "https://refed.org/solutions",
    ]
    out = []
    for url in seeds:
        try:
            r = fc.scrape_url(url, params={"formats": ["markdown"]})
            out.append({"source": url, "content": r})
        except Exception as e:
            print(f"⚠ {url}: {e}")
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    print("→ EPA banned plastics")
    (OUT / "epa_banned_raw.json").write_text(json.dumps(scrape_epa_banned_plastics(), indent=2))

    print("→ BioCycle compost facilities")
    (OUT / "compost_facilities.json").write_text(json.dumps(scrape_biocycle_compost(), indent=2))

    print("→ Enzyme labs")
    (OUT / "labs.json").write_text(json.dumps(scrape_enzyme_labs(), indent=2))

    print("✅ Firecrawl jobs done. Hand-curate into data/epa_banned.json schema:")
    print('   { "PS": ["CA","NY","ME"], "PVC": ["..."], ... }')


if __name__ == "__main__":
    main()
