from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://aletheia_user:aletheia_password@localhost:5435/aletheia_db"
    GEMINI_API_KEY: str = ""
    GITHUB_TOKEN: str = ""
    GITHUB_REPOSITORY: str = ""
    GITHUB_BASE_BRANCH: str = "main"
    REPO_PATH: str = "."
    API_KEY: str = ""
    WEBHOOK_SECRET: str = ""
    REDIS_URL: str = "redis://127.0.0.1:6379/0"
    ENVIRONMENT: str = "development"
    MAX_ERROR_LOG_LENGTH: int = 100_000
    MAX_PATCH_LENGTH: int = 500_000
    MAX_CONCURRENT_JOBS: int = 2
    FRONTEND_ORIGINS: str = "http://127.0.0.1:5174,http://localhost:5174"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
