from urllib.parse import urlparse

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Repperoni"
    app_base_url: str | None = None
    database_url: str = "sqlite+aiosqlite:///./repperoni.db"
    secret_key: str = "change-me-in-production"
    access_token_expire_minutes: int = Field(default=60, ge=5, le=60 * 24)
    session_max_age_seconds: int = 60 * 60 * 24 * 180
    session_idle_timeout_seconds: int = 60 * 60 * 24 * 28
    auth_flow_expire_seconds: int = 10 * 60
    secure_cookies: bool = False
    webauthn_rp_id: str | None = None
    webcredentials_apps: list[str] = []
    cors_origins: list[str] = []
    auto_migrate: bool = True

    @field_validator("app_base_url", mode="before")
    @classmethod
    def normalize_base_url(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip().rstrip("/")
        if not normalized:
            return None
        parsed = urlparse(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("app_base_url must be an http or https URL")
        return normalized

    @field_validator("webcredentials_apps", "cors_origins", mode="before")
    @classmethod
    def split_lists(cls, value: object) -> object:
        if value is None:
            return []
        if isinstance(value, str):
            return [entry.strip() for entry in value.split(",") if entry.strip()]
        return value


settings = Settings()
