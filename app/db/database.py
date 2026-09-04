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

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

logger = logging.getLogger("aletheia")


def _normalise_database_url(url: str) -> str:
    """Convert a Neon/standard postgres URL to asyncpg-compatible format.

    Handles two common mismatches:
    1. Plain `postgresql://` → `postgresql+asyncpg://`
    2. `sslmode=require`    → `ssl=require` (asyncpg parameter name)
    """
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
        "postgresql+asyncpg://aletheia_user:aletheia_password@localhost:5435/aletheia_db",
    )
)

# Connection pool settings tuned for a medium-load async API.
# pool_size=10 keeps 10 persistent connections open.
# max_overflow=20 allows up to 30 total under burst.
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,  # Verify connection health before each use
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
