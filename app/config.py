"""
Application configuration.

All values are read from environment variables first, then from a `.env` file
in the working directory. Every setting has a safe default for local development.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str = (
        "postgresql+asyncpg://aletheia_user:aletheia_password@localhost:5435/aletheia_db"
    )

    # ── AI ────────────────────────────────────────────────────────────────────
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.6-flash"

    # ── GitHub ────────────────────────────────────────────────────────────────
    GITHUB_TOKEN: str = ""
    GITHUB_REPOSITORY: str = ""
    GITHUB_BASE_BRANCH: str = "main"
    REPO_PATH: str = "."

    # ── Security ──────────────────────────────────────────────────────────────
    API_KEY: str = ""
    WEBHOOK_SECRET: str = ""

    # ── Redis / Queue ─────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://127.0.0.1:6379/0"
    # Number of ARQ worker coroutines processing jobs concurrently
    WORKER_CONCURRENCY: int = 4
    # How long (seconds) a finished job result stays in Redis before expiry
    REDIS_JOB_TTL: int = 86_400  # 24 hours

    # ── Rate Limiting ─────────────────────────────────────────────────────────
    # Max ingest requests per client IP per RATE_LIMIT_WINDOW seconds
    RATE_LIMIT_MAX_REQUESTS: int = 30
    RATE_LIMIT_WINDOW_SECONDS: int = 60
    # How long (seconds) an idempotency key is remembered
    IDEMPOTENCY_TTL_SECONDS: int = 3_600  # 1 hour

    # ── Patch limits ──────────────────────────────────────────────────────────
    MAX_ERROR_LOG_LENGTH: int = 100_000
    MAX_PATCH_LENGTH: int = 500_000

    # ── Concurrency ───────────────────────────────────────────────────────────
    MAX_CONCURRENT_JOBS: int = 4

    # ── CORS ──────────────────────────────────────────────────────────────────
    FRONTEND_ORIGINS: str = "http://127.0.0.1:5174,http://localhost:5174"

    # ── Runtime ───────────────────────────────────────────────────────────────
    # "development" skips API-key enforcement; "production" enforces all guards
    ENVIRONMENT: str = "development"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
