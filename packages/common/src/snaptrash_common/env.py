from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in [here, *here.parents]:
        if (parent / ".env.example").exists():
            return parent
    return Path.cwd()


REPO_ROOT = _find_repo_root()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Databricks
    DATABRICKS_HOST: str = ""
    DATABRICKS_TOKEN: str = ""
    DATABRICKS_WAREHOUSE_ID: str = ""
    DATABRICKS_CATALOG: str = "workspace"
    DATABRICKS_SCHEMA: str = "snaptrash"

    # AWS
    AWS_REGION: str = "us-west-2"
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    S3_BUCKET: str = "snaptrash-bins"

    # APIs
    GROQ_API_KEY: str = ""
    GROQ_VISION_MODEL: str = "llama-4-scout-17b-16e-instruct"
    FIRECRAWL_API_KEY: str = ""
    SENDGRID_API_KEY: str = ""
    SENDGRID_FROM_EMAIL: str = "alerts@snaptrash.app"
    USDA_API_KEY: str = ""
    MAPBOX_TOKEN: str = ""

    # App
    ENV: str = "dev"
    LOG_LEVEL: str = "INFO"
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    CORS_ORIGINS: str = "http://localhost:5173"

    @property
    def fq_schema(self) -> str:
        return f"{self.DATABRICKS_CATALOG}.{self.DATABRICKS_SCHEMA}"

    def fq_table(self, name: str) -> str:
        return f"{self.fq_schema}.{name}"


settings = Settings()
