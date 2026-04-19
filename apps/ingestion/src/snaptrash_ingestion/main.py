import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from snaptrash_common import settings
from .routes import health, scan, analytics

_REQUIRED = ["DATABRICKS_HOST", "DATABRICKS_TOKEN", "DATABRICKS_WAREHOUSE_ID", "S3_BUCKET"]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)

app = FastAPI(title="SnapTrash Ingestion API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.CORS_ORIGINS.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(scan.router)
app.include_router(analytics.router)


@app.on_event("startup")
def validate_settings():
    missing = [k for k in _REQUIRED if not getattr(settings, k, None)]
    if missing:
        raise RuntimeError(f"Missing required env vars: {', '.join(missing)}")


@app.get("/")
def root():
    return {"service": "snaptrash-ingestion", "env": settings.ENV}
