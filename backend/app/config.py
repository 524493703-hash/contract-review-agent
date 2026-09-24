from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(BASE_DIR / ".env", BASE_DIR / ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "契析 · AI合同审核智能体"
    environment: str = "development"
    database_url: str = f"sqlite:///{(BASE_DIR / 'data' / 'contract_review.db').as_posix()}"
    db_pool_size: int = 10
    db_max_overflow: int = 10
    db_pool_recycle_seconds: int = 120
    db_pool_pre_ping: bool = True
    auth_cache_seconds: int = 60
    jwt_secret: str = "replace-this-secret-before-production"
    jwt_expire_minutes: int = 720
    demo_mode: bool = True
    initial_password: str = "Poc@2026"
    upload_dir: Path = BASE_DIR / "data" / "uploads"
    export_dir: Path = BASE_DIR / "data" / "exports"
    cors_origins: str = "http://localhost:3000,http://localhost:5173,http://localhost:8080"
    sso_enabled: bool = False
    llm_api_url: str | None = "https://api.deepseek.com"
    llm_api_key: str | None = None
    llm_model: str = "deepseek-v4-pro"
    focused_check_model: str | None = None
    legacy_rule_mode: str = "shadow"

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.export_dir.mkdir(parents=True, exist_ok=True)
    if settings.database_url.startswith("sqlite"):
        (BASE_DIR / "data").mkdir(parents=True, exist_ok=True)
    return settings
