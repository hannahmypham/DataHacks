from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from snaptrash_common import settings
from .routes import health, scan

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


@app.get("/")
def root():
    return {"service": "snaptrash-ingestion", "env": settings.ENV}
