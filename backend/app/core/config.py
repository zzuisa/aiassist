"""Typed application settings with secret-file loading and dependency health.

Configuration comes from environment variables (see `.env.example`). Secrets are
loaded from files referenced by ``*_FILE`` env vars so plaintext never lives in
the environment or compose file. Optional providers (mail, LLM, speech) degrade
gracefully when unconfigured instead of blocking base persistence.
"""

from __future__ import annotations

import os
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppEnv(StrEnum):
    development = "development"
    production = "production"
    test = "test"


class DependencyStatus(StrEnum):
    ready = "ready"
    degraded = "degraded"
    unconfigured = "unconfigured"


def _read_secret_file(path: str | None) -> str | None:
    """Return the stripped contents of a secret file, or None if absent/empty."""
    if not path:
        return None
    p = Path(path)
    if not p.is_file():
        return None
    value = p.read_text(encoding="utf-8").strip()
    return value or None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Read a local .env when present (repo root). Docker Compose still injects
        # the same file via env_file:, and OS env vars take precedence over the
        # file, so this only adds standalone/dev support — no production change.
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # -- application --
    app_env: AppEnv = AppEnv.development
    app_base_url: str = "http://localhost:5173"
    app_timezone: str = "Europe/Berlin"
    app_default_locale: str = "zh-CN"
    log_level: str = "INFO"
    app_allowed_origins: str = "http://localhost:5173"

    # -- database --
    database_url: str | None = None
    postgres_db: str = "aiassist"
    postgres_user: str = "aiassist"
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_password_file: str | None = None
    postgres_password: str | None = None

    # -- redis --
    redis_url: str | None = None
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_db: int = 0

    # -- rabbitmq --
    amqp_url: str | None = None
    rabbitmq_host: str = "rabbitmq"
    rabbitmq_port: int = 5672
    rabbitmq_user: str = "aiassist"
    rabbitmq_vhost: str = "aiassist"
    rabbitmq_password_file: str | None = None
    rabbitmq_password: str | None = None

    # -- object storage --
    storage_provider: str = "local"
    asset_root: str = "/data/assets"
    s3_endpoint_url: str = ""
    s3_bucket: str = "aiassist"
    s3_region: str = "us-east-1"

    # -- auth --
    jwt_signing_key_file: str | None = None
    jwt_signing_key: str | None = None
    access_token_ttl_seconds: int = 900
    refresh_token_ttl_seconds: int = 1209600
    login_max_attempts: int = 10
    login_window_seconds: int = 900

    # -- uploads --
    upload_image_max_bytes: int = 26214400
    upload_audio_max_bytes: int = 52428800
    upload_markdown_max_bytes: int = 2097152
    upload_image_max_pixels: int = 50000000

    # -- recurrence --
    recurrence_lookahead_days: int = Field(default=1, ge=1, le=7)

    # -- mail (optional) --
    smtp_host: str = ""
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_from: str = "AI Assist <noreply@example.com>"
    smtp_tls_mode: str = "implicit"
    smtp_password_file: str | None = None
    smtp_password: str | None = None

    # -- llm / speech (optional) --
    llm_provider: str = "none"
    llm_base_url: str = ""
    llm_default_model: str = ""
    # Model generation is asynchronous, but every external socket operation
    # remains bounded so a half-open provider cannot occupy a worker forever.
    llm_connect_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    llm_read_timeout_seconds: float = Field(default=300.0, gt=0, le=900)
    llm_max_output_tokens: int = Field(default=6144, ge=512, le=32768)
    # JSON list of locally registered blog enhancement capabilities.  Only
    # non-secret manifest fields are exposed to the model orchestrator.
    blog_capabilities_json: str = ""
    blog_allow_retrieved_images: bool = False
    blog_allow_generated_images: bool = False
    # Agent fan-out runs inside the single worker-heavy process. Keep both
    # dimensions bounded so one batch cannot monopolize voice/image workloads.
    agent_max_batch_objects: int = Field(default=200, ge=1, le=500)
    agent_max_concurrency: int = Field(default=4, ge=1, le=8)
    speech_provider: str = "none"
    speech_default_model: str = ""
    llm_provider_key_file: str | None = None
    llm_provider_key: str | None = None

    # -- Radio / Bilibili transcription (optional external service) --
    radio_service_base_url: str = ""
    radio_service_connect_timeout_seconds: float = Field(default=5.0, gt=0, le=60)
    radio_service_read_timeout_seconds: float = Field(default=30.0, gt=0, le=300)
    radio_service_poll_interval_seconds: int = Field(default=10, ge=2, le=300)
    radio_service_max_wait_seconds: int = Field(default=21600, ge=60, le=86400)
    radio_service_password_file: str | None = None
    radio_service_password: str | None = None

    backup_retention_days: int = 30

    # -- MCP (Model Context Protocol) tool gateway (optional) --
    # Endpoints, tokens and connection strings live only in this file, keyed by
    # config_key. The database stores config_key + safe metadata only — never
    # the file contents. See deploy/secrets/mcp-connections.example.json.
    mcp_secrets_file: str | None = None
    mcp_connect_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    mcp_read_timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    mcp_max_result_bytes: int = Field(default=262144, ge=1024, le=4194304)
    mcp_catalog_ttl_seconds: int = Field(default=300, ge=30, le=3600)
    mcp_max_retries: int = Field(default=2, ge=0, le=5)
    mcp_max_connections_per_user: int = Field(default=20, ge=1, le=100)
    mcp_max_visible_tools: int = Field(default=100, ge=1, le=500)
    # Turn/task heartbeat watchdog thresholds (used by the beat-scheduled
    # stalled-work repair job; see app/modules/agent/watchdog.py).
    agent_turn_heartbeat_timeout_seconds: int = Field(default=45, ge=10, le=600)
    agent_turn_watchdog_interval_seconds: int = Field(default=30, ge=5, le=300)

    # ---------------------------------------------------------------- secrets

    @computed_field  # type: ignore[prop-decorator]
    @property
    def resolved_postgres_password(self) -> str | None:
        return _read_secret_file(self.postgres_password_file) or self.postgres_password

    @computed_field  # type: ignore[prop-decorator]
    @property
    def resolved_jwt_signing_key(self) -> str | None:
        return _read_secret_file(self.jwt_signing_key_file) or self.jwt_signing_key

    @computed_field  # type: ignore[prop-decorator]
    @property
    def resolved_rabbitmq_password(self) -> str | None:
        return _read_secret_file(self.rabbitmq_password_file) or self.rabbitmq_password

    @computed_field  # type: ignore[prop-decorator]
    @property
    def resolved_smtp_password(self) -> str | None:
        return _read_secret_file(self.smtp_password_file) or self.smtp_password

    @computed_field  # type: ignore[prop-decorator]
    @property
    def resolved_llm_provider_key(self) -> str | None:
        return _read_secret_file(self.llm_provider_key_file) or self.llm_provider_key

    @computed_field  # type: ignore[prop-decorator]
    @property
    def resolved_radio_service_password(self) -> str | None:
        return _read_secret_file(self.radio_service_password_file) or self.radio_service_password

    @property
    def mcp_secrets_path(self) -> Path | None:
        if not self.mcp_secrets_file:
            return None
        p = Path(self.mcp_secrets_file)
        return p if p.is_file() else None

    # ------------------------------------------------------------ connections

    @property
    def sqlalchemy_url(self) -> str:
        if self.database_url:
            return self.database_url
        pw = self.resolved_postgres_password or ""
        return (
            f"postgresql+psycopg://{quote(self.postgres_user, safe='')}:"
            f"{quote(pw, safe='')}@{self.postgres_host}:{self.postgres_port}/"
            f"{quote(self.postgres_db, safe='')}"
        )

    @property
    def redis_dsn(self) -> str:
        if self.redis_url:
            return self.redis_url
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def amqp_dsn(self) -> str:
        if self.amqp_url:
            return self.amqp_url
        pw = self.resolved_rabbitmq_password or ""
        return (
            f"amqp://{quote(self.rabbitmq_user, safe='')}:{quote(pw, safe='')}"
            f"@{self.rabbitmq_host}:{self.rabbitmq_port}/"
            f"{quote(self.rabbitmq_vhost, safe='')}"
        )

    @property
    def allowed_origins(self) -> list[str]:
        return [o.strip() for o in self.app_allowed_origins.split(",") if o.strip()]

    # ------------------------------------------------------------ dependency states

    def mail_status(self) -> DependencyStatus:
        if not self.smtp_host:
            return DependencyStatus.unconfigured
        return DependencyStatus.ready if self.resolved_smtp_password else DependencyStatus.degraded

    def llm_status(self) -> DependencyStatus:
        if self.llm_provider == "none":
            return DependencyStatus.unconfigured
        if self.llm_provider == "ollama":
            return DependencyStatus.ready
        has_key = bool(self.resolved_llm_provider_key)
        return DependencyStatus.ready if has_key else DependencyStatus.degraded

    def speech_status(self) -> DependencyStatus:
        if self.speech_provider == "none":
            return DependencyStatus.unconfigured
        if self.speech_provider == "faster_whisper":
            return DependencyStatus.ready
        has_key = bool(self.resolved_llm_provider_key)
        return DependencyStatus.ready if has_key else DependencyStatus.degraded

    def storage_status(self) -> DependencyStatus:
        return DependencyStatus.ready

    def mcp_status(self) -> DependencyStatus:
        return DependencyStatus.ready if self.mcp_secrets_path else DependencyStatus.unconfigured

    def validate_startup(self) -> None:
        """Fail fast when a production-required secret is missing."""
        if self.app_env is not AppEnv.production:
            return
        missing: list[str] = []
        if not self.resolved_jwt_signing_key:
            missing.append("jwt_signing_key")
        if not self.resolved_postgres_password and not self.database_url:
            missing.append("postgres_password")
        if not self.resolved_rabbitmq_password and not self.amqp_url:
            missing.append("rabbitmq_password")
        if missing:
            raise RuntimeError(f"Missing required production secrets: {', '.join(missing)}")


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reload_settings() -> Settings:
    """Clear the cache and re-read the environment (used by tests)."""
    get_settings.cache_clear()
    return get_settings()


# Test databases and CI provide a signing key via env; local dev falls back to a
# clearly non-production ephemeral key so the app can boot without secret files.
def ensure_dev_signing_key() -> None:
    s = get_settings()
    if s.app_env is not AppEnv.production and not s.resolved_jwt_signing_key:
        os.environ.setdefault("JWT_SIGNING_KEY", "dev-insecure-signing-key-change-me")
        reload_settings()
