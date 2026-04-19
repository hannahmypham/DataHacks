"""
Settings loader — reads from environment variables (+ optional .env file).
No pydantic-settings dependency: works on Databricks serverless without conflicts.
"""
from __future__ import annotations
import os
import pathlib


def _load_dotenv() -> None:
    """Load .env file from repo root if present (dev/local only)."""
    here = pathlib.Path(__file__).resolve()
    for parent in [here, *here.parents]:
        try:
            env_file = parent / ".env"
            if env_file.is_file():
                for line in env_file.read_text().splitlines():
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())
                return
        except (OSError, PermissionError):
            # Volume paths raise Errno 22 on stat calls
            continue


_load_dotenv()


def _str(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def _int(key: str, default: int = 0) -> int:
    try:
        return int(os.environ.get(key, str(default)))
    except (ValueError, TypeError):
        return default


class _Settings:
    # Databricks
    DATABRICKS_HOST: str = _str("DATABRICKS_HOST")
    DATABRICKS_TOKEN: str = _str("DATABRICKS_TOKEN")
    DATABRICKS_WAREHOUSE_ID: str = _str("DATABRICKS_WAREHOUSE_ID")
    DATABRICKS_CATALOG: str = _str("DATABRICKS_CATALOG", "workspace")
    DATABRICKS_SCHEMA: str = _str("DATABRICKS_SCHEMA", "snaptrash")

    # AWS
    AWS_REGION: str = _str("AWS_REGION", "us-west-2")
    AWS_ACCESS_KEY_ID: str = _str("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY: str = _str("AWS_SECRET_ACCESS_KEY")
    S3_BUCKET: str = _str("S3_BUCKET", "snaptrash-bins")

    # APIs
    GROQ_API_KEY: str = _str("GROQ_API_KEY")
    GROQ_VISION_MODEL: str = _str("GROQ_VISION_MODEL", "llama-4-scout-17b-16e-instruct")
    FIRECRAWL_API_KEY: str = _str("FIRECRAWL_API_KEY")
    SENDGRID_API_KEY: str = _str("SENDGRID_API_KEY")
    SENDGRID_FROM_EMAIL: str = _str("SENDGRID_FROM_EMAIL", "alerts@snaptrash.app")
    USDA_API_KEY: str = _str("USDA_API_KEY")
    MAPBOX_TOKEN: str = _str("MAPBOX_TOKEN")

    # App
    ENV: str = _str("ENV", "dev")
    LOG_LEVEL: str = _str("LOG_LEVEL", "INFO")
    API_HOST: str = _str("API_HOST", "0.0.0.0")
    API_PORT: int = _int("API_PORT", 8000)
    CORS_ORIGINS: str = _str("CORS_ORIGINS", "http://localhost:5173")

    @property
    def fq_schema(self) -> str:
        return f"{self.DATABRICKS_CATALOG}.{self.DATABRICKS_SCHEMA}"

    def fq_table(self, name: str) -> str:
        return f"{self.fq_schema}.{name}"


settings = _Settings()
