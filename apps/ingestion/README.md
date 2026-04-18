# Ingestion App (Person A)

Stages 1–5 of SnapTrash pipeline:

1. Image upload → AWS S3
2. Groq Vision → JSON (food + plastic items)
3. Food analysis (USDA shelf life, $, CO₂)
4. Plastic analysis (resin → polymer, EPA flags)
5. Write `ScanRow` to `snaptrash.scans` Delta table

## Run

```bash
uv sync
uv run uvicorn snaptrash_ingestion.main:app --reload --port 8000
```

## Endpoints

- `GET  /health`
- `POST /scan` — multipart upload, returns scan_id + analysis JSON

## Integration handoff

Writes only to `snaptrash.scans` (schema in `packages/common/.../tables.py` + `schemas.py::ScanRow`).
Person B reads from this table downstream — do **not** rename columns without coordinating.
