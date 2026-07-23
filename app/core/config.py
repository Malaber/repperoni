from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


DEPLOYED_ENVIRONMENTS = {"production", "review"}
LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost", "testserver"}
PLACEHOLDER_SECRET = "change-me-in-production"
RegistrationMode = Literal["closed", "first-user", "open"]


def _normalized_origin(value: str, *, field_name: str) -> str:
    normalized = value.strip().rstrip("/")
    parsed = urlparse(normalized)
    try:
        parsed.port
    except ValueError as exc:
        raise ValueError(f"{field_name} has an invalid port") from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(f"{field_name} must be an http or https origin")
    return normalized


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Repperoni"
    app_version: str = Field(default="dev", min_length=1, max_length=64)
    app_revision: str = Field(
        default="unknown",
        pattern=r"^(?:unknown|[0-9a-f]{40})$",
    )
    environment: Literal["development", "test", "review", "production"] = "development"
    registration_mode: RegistrationMode = "first-user"
    app_base_url: str | None = None
    database_url: str = "sqlite+aiosqlite:///./repperoni.db"
    secret_key: str = PLACEHOLDER_SECRET
    access_token_expire_minutes: int = Field(default=60, ge=5, le=60 * 24)
    session_max_age_seconds: int = 60 * 60 * 24 * 180
    session_idle_timeout_seconds: int = 60 * 60 * 24 * 28
    auth_flow_expire_seconds: int = 10 * 60
    max_request_body_bytes: int = Field(default=64 * 1024, ge=1024, le=1024 * 1024)
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
        if not value.strip():
            return None
        return _normalized_origin(value, field_name="app_base_url")

    @field_validator("webcredentials_apps", "cors_origins", mode="before")
    @classmethod
    def split_lists(cls, value: object) -> object:
        if value is None:
            return []
        if isinstance(value, str):
            return [entry.strip() for entry in value.split(",") if entry.strip()]
        return value

    @field_validator("cors_origins")
    @classmethod
    def validate_cors_origins(cls, values: list[str]) -> list[str]:
        if "*" in values:
            raise ValueError("cors_origins must list exact origins")
        return [_normalized_origin(value, field_name="cors_origins") for value in values]

    @field_validator("webauthn_rp_id")
    @classmethod
    def normalize_rp_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower().rstrip(".")
        if (
            not normalized
            or "://" in normalized
            or "/" in normalized
            or ":" in normalized
            or urlparse(f"//{normalized}").hostname != normalized
        ):
            raise ValueError("webauthn_rp_id must be a hostname")
        return normalized

    @model_validator(mode="after")
    def validate_security_contract(self):
        base = urlparse(self.app_base_url) if self.app_base_url else None
        hostname = base.hostname.lower() if base and base.hostname else None
        if base and base.scheme == "http" and hostname not in LOCAL_HOSTS:
            raise ValueError("non-local app_base_url must use https")
        if self.webauthn_rp_id and hostname:
            if hostname != self.webauthn_rp_id and not hostname.endswith(f".{self.webauthn_rp_id}"):
                raise ValueError("webauthn_rp_id must equal or contain app_base_url")
        if self.environment in DEPLOYED_ENVIRONMENTS:
            if not base or base.scheme != "https":
                raise ValueError("deployed environments require an https app_base_url")
            if not self.secure_cookies:
                raise ValueError("deployed environments require secure cookies")
            if self.secret_key == PLACEHOLDER_SECRET or len(self.secret_key) < 32:
                raise ValueError("deployed environments require a 32-character secret key")
            if not self.webauthn_rp_id:
                raise ValueError("deployed environments require webauthn_rp_id")
        return self

    @property
    def deployed(self) -> bool:
        return self.environment in DEPLOYED_ENVIRONMENTS

    @property
    def session_cookie_name(self) -> str:
        return "__Host-repperoni-session" if self.secure_cookies else "repperoni-session"

    @property
    def trusted_hosts(self) -> list[str]:
        hosts = {"127.0.0.1", "localhost"}
        if self.environment == "test":
            hosts.add("testserver")
        if self.app_base_url and (hostname := urlparse(self.app_base_url).hostname):
            hosts.add(hostname)
        return sorted(hosts)

    @property
    def trusted_origins(self) -> frozenset[str]:
        origins = set(self.cors_origins)
        if self.app_base_url:
            origins.add(self.app_base_url)
        return frozenset(origins)


settings = Settings()
