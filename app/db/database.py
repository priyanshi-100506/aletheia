"""
Database session utilities.

Provides the SQLAlchemy async engine, session factory, and a FastAPI
dependency for injecting database sessions into endpoint handlers.

Neon compatibility:
    Neon's dashboard provides connection strings with `sslmode=require`.
    asyncpg uses `ssl=require` instead. This module auto-converts the URL
    so you can paste Neon's string directly into DATABASE_URL.
"""
import os
import logging
from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

logger = logging.getLogger("aletheia")


def _normalise_database_url(url: str) -> str:
    """Convert standard postgres or sqlite URLs to async-compatible format."""
    if url.startswith("sqlite://") and "+aiosqlite" not in url:
        return url.replace("sqlite://", "sqlite+aiosqlite://", 1)
    if url.startswith("postgresql://") and "+asyncpg" not in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://") and "+asyncpg" not in url:
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    # asyncpg uses ssl=require, not sslmode=require
    url = url.replace("sslmode=require", "ssl=require")
    return url


DATABASE_URL: str = _normalise_database_url(
    os.getenv(
        "DATABASE_URL",
        "sqlite+aiosqlite:///./aletheia_dev.db",
    )
)

is_sqlite = DATABASE_URL.startswith("sqlite")
engine_kwargs = {"echo": False}
if not is_sqlite:
    engine_kwargs.update({"pool_size": 10, "max_overflow": 20, "pool_pre_ping": True})

engine = create_async_engine(
    DATABASE_URL,
    **engine_kwargs
)


AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,  # Avoid lazy-load errors after commit
)


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""
    pass


async def init_db() -> None:
    """Create all tables that don't already exist.

    Called once at application startup. Does NOT run migrations —
    use Alembic for schema changes in production.
    """
    # Import all models so their metadata is registered with Base
    from app.models.remediation import RemediationJob  # noqa: F401
    from app.models.audit import AuditLog  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if conn.dialect.name == "postgresql":
            for status in (
                "PATCH_APPLIED",
                "VALIDATION_PASSED",
                "VALIDATION_FAILED",
                "WAIT_FOR_APPROVAL",
                "APPROVING",
            ):
                await conn.execute(text(
                    f"ALTER TYPE patchstatus ADD VALUE IF NOT EXISTS '{status}'"
                ))
            await conn.execute(text(
                "ALTER TABLE remediation_jobs "
                "ADD COLUMN IF NOT EXISTS target_test VARCHAR(256), "
                "ADD COLUMN IF NOT EXISTS baseline_target_result TEXT, "
                "ADD COLUMN IF NOT EXISTS postfix_target_result TEXT, "
                "ADD COLUMN IF NOT EXISTS baseline_full_result TEXT, "
                "ADD COLUMN IF NOT EXISTS postfix_full_result TEXT, "
                "ADD COLUMN IF NOT EXISTS evidence_json TEXT, "
                "ADD COLUMN IF NOT EXISTS repository VARCHAR(512), "
                "ADD COLUMN IF NOT EXISTS base_sha VARCHAR(64), "
                "ADD COLUMN IF NOT EXISTS pr_url VARCHAR(1024), "
                "ADD COLUMN IF NOT EXISTS pr_number INTEGER, "
                "ADD COLUMN IF NOT EXISTS pr_simulated BOOLEAN NOT NULL DEFAULT FALSE"
            ))


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a database session.

    Usage:
        @router.get("/example")
        async def handler(db: AsyncSession = Depends(get_db)):
            ...

    The session is automatically closed after the request completes,
    even if an exception is raised.
    """
    async with AsyncSessionLocal() as session:
        yield session
