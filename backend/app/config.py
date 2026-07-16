"""Application configuration, loaded from environment variables / .env."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- App ----
    app_name: str = "Telegram Marketing CRM"
    app_version: str = "0.1.0"
    environment: str = "development"
    debug: bool = True

    # ---- API / Auth ----
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    cors_origins: str = "*"

    # ---- Bootstrap admin (created by `python -m app.cli ensure-admin`) ----
    bootstrap_admin_email: str = "admin@example.com"
    bootstrap_admin_password: str = "admin12345"
    bootstrap_admin_name: str = "Administrator"

    # ---- PostgreSQL ----
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_user: str = "crm"
    postgres_password: str = "crm"
    postgres_db: str = "telegram_crm"

    # ---- Redis ----
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_db: int = 0

    # ---- Optional full database URL override (12-factor DATABASE_URL) ----
    # When set, it takes precedence over the POSTGRES_* parts above. Use an
    # async-capable driver, e.g. postgresql+psycopg://... or
    # sqlite+aiosqlite:///./local.db
    database_url_env: str = Field(default="", validation_alias="DATABASE_URL")

    # ---- Telegram (shared API credentials) ----
    telegram_api_id: str = ""
    telegram_api_hash: str = ""

    # ---- Telegram Engine Service ----
    # Internal URL the backend uses to reach the engine's private HTTP API.
    engine_url: str = "http://engine:9100"
    engine_timeout_seconds: float = 30.0
    # Where the engine persists Telethon session files (mounted volume).
    sessions_dir: str = "./sessions"

    # ---- Safety / anti-ban (Phase 3; overridable from Settings later) ----
    # Auto-quarantine an account when a health check reports it is limited/flagged.
    auto_quarantine_on_warning: bool = True

    # ---- Warmup (Phase 4; overridable from Settings later) ----
    warmup_full_daily_cap: int = 30

    # ---- Sender / anti-ban (Phase 7; overridable from Settings later) ----
    send_min_delay_seconds: int = 40
    send_max_delay_seconds: int = 180

    # ---- Backup & restore center (Phase 15.2) ----
    # Where backup archives are written (a mounted volume in Docker).
    backup_dir: str = "./backups"
    # How many archives to keep — older ones are pruned automatically.
    backup_keep_last: int = 5
    # Largest backup archive accepted by the upload/load endpoint.
    backup_max_upload_mb: int = 500

    # ---- Security / hardening (Phase 12) ----
    # Per-client-IP request rate limiting (fixed window of `rate_limit_window_seconds`).
    rate_limit_enabled: bool = True
    rate_limit_per_minute: int = 240  # global default for /api/* per IP
    rate_limit_login_per_minute: int = 10  # tighter cap for auth endpoints (brute-force)
    rate_limit_window_seconds: int = 60
    # Emit standard security response headers (HSTS, nosniff, frame-deny, ...).
    security_headers_enabled: bool = True
    # Send HSTS (only meaningful behind HTTPS; safe to leave on — browsers ignore on http).
    hsts_enabled: bool = True
    hsts_max_age: int = 31536000  # 1 year

    @property
    def is_production(self) -> bool:
        return self.environment.strip().lower() == "production"

    def insecure_production_defaults(self) -> list[str]:
        """Return a list of insecure default settings that must not ship to prod.

        Empty when the configuration is safe. Used by the startup guard and the
        ``app.cli prod-check`` command.
        """
        problems: list[str] = []
        if self.secret_key == "change-me-in-production" or len(self.secret_key) < 16:
            problems.append("SECRET_KEY is unset/default/too short (use `openssl rand -hex 32`)")
        if self.bootstrap_admin_password == "admin12345":
            problems.append("BOOTSTRAP_ADMIN_PASSWORD is the default value")
        if self.postgres_password in ("crm", "", "postgres") and not self.database_url_env:
            problems.append("POSTGRES_PASSWORD is a weak default")
        if self.cors_origin_list == ["*"]:
            problems.append("CORS_ORIGINS is '*' (set your domain in production)")
        if self.debug:
            problems.append("DEBUG is true (set DEBUG=false in production)")
        return problems

    @property
    def cors_origin_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def database_url(self) -> str:
        """Async SQLAlchemy URL. Honors DATABASE_URL if provided."""
        if self.database_url_env:
            return self.database_url_env
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def sync_database_url(self) -> str:
        """Synchronous URL used by Alembic migrations (derived from database_url)."""
        return (
            self.database_url.replace("+aiosqlite", "").replace("+asyncpg", "+psycopg")
        )

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
