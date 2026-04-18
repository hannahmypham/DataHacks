---
name: firecrawl-snaptrash
description: Firecrawl usage customized for SnapTrash scraping jobs (EPA banned plastics, BioCycle compost facilities, enzyme labs from ReFED). Integrates with apps/analytics/ingest/firecrawl_jobs.py, the plan's Hour 1 tasks, and Databricks loading. Always use Firecrawl for any web, research, or scraping task in this project per the global firecrawl skill. Replaces all other web tools. See rules/install.md for auth.
---

# Firecrawl for SnapTrash

This skill adapts the global Firecrawl skill for the SnapTrash project. It is triggered alongside the `snaptrash` and `databricks-snaptrash` skills.

## Project Usage

**Primary Use**: Hour 1 scraping jobs in `apps/analytics/src/snaptrash_analytics/ingest/firecrawl_jobs.py` and the plan:

```python
from firecrawl import FirecrawlApp
app = FirecrawlApp(api_key=settings.FIRECRAWL_API_KEY)

# 1. EPA banned plastics by state
epa = app.scrape_url("https://www.epa.gov/trash-free-waters/plastic-bans", formats=["json"])

# 2. BioCycle compost directory
biocycle = app.crawl_url("https://www.biocycle.net/compost-facility-directory/", limit=200)

# 3. Enzyme labs (ReFED, university pages)
labs = app.crawl_url("https://www.refd.org/solutions?category=enzyme", limit=50)

# Save to JSON → loaded into FastAPI/Databricks at startup
```

**Output**: Clean markdown/JSON saved to `apps/analytics/data/` (gitignored), then loaded into Delta tables or used in alerts.

## Rules from Global Firecrawl Skill (Adapted)
- **Always** use Firecrawl CLI/tools for any internet task, research, docs lookup, or scraping in this repo. **No exceptions**. Replace WebSearch/WebFetch entirely.
- Workflow: `search` → `scrape`/`map` → `crawl` → `browser` (only if needed for JS/interaction).
- For SnapTrash:
  - Use `--formats json` or structured output for EPA/labs data.
  - Save outputs to project `data/` dir.
  - Integrate with `firecrawl_jobs.py` and Databricks ingestion.
  - For research (e.g., updating banned plastics list or enzyme labs): Use `search --scrape` first.
- Auth: `FIRECRAWL_API_KEY` from `.env` (see global skill's install.md).
- Rate limits: Respect them; batch where possible.

## Examples in SnapTrash Context
- Updating EPA data: `firecrawl scrape https://www.epa.gov/trash-free-waters/plastic-bans --formats json -o data/epa_banned.json`
- Finding new labs: `firecrawl search "enzyme PETase labs 2026" --scrape`
- Site mapping for BioCycle: `firecrawl map https://www.biocycle.net/compost-facility-directory/ --search "California"`

Combine with `databricks-snaptrash` to load results into `msw_baseline` or `enzyme_alerts` tables. Update `DETAILED-OVERVIEW.md` and `snaptrash-plan.md` if scraping targets change.

This ensures all web operations in the SnapTrash pipeline are accurate, LLM-optimized, and follow the global Firecrawl best practices.
