"""
ALETHEIA FastAPI application entry point.

Startup sequence:
    1. Load .env file
    2. Connect to Redis (required) — fail fast if unavailable in production
    3. Connect to PostgreSQL (required) — run init_db to create tables
    4. Optionally start in-process ARQ worker (set RUN_WORKER_INPROCESS=true)
    5. Mount API router

Shutdown sequence:
    1. Cancel in-process worker task (if running)
    2. Close Redis connection pool

The `lifespan` async context manager handles startup and shutdown in a
single function, which is the modern FastAPI pattern (replaces @app.on_event).

In-process worker mode (RUN_WORKER_INPROCESS=true):
    On free hosting platforms (Render free tier) where running two services
    would exhaust the 750 h/month limit, set this env var to run the ARQ
    worker inside the same process as the API server. It shares the same
    event loop and Redis connection. This trades strict process isolation for
    zero additional cost.
"""
import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from dotenv import load_dotenv

load_dotenv()  # Must run before any settings import reads env vars

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.v1.router import api_router
from app.config import settings
from app.db.database import engine, init_db
from app.services.redis_store import close_redis_pool, init_redis_pool

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("aletheia")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application startup and shutdown."""
    _worker_task: asyncio.Task | None = None

    # ── Redis ─────────────────────────────────────────────────────────────────
    try:
        redis_pool = await init_redis_pool()
        app.state.redis = redis_pool
        logger.info("Redis ready")
    except Exception as exc:
        if settings.ENVIRONMENT == "production":
            logger.critical("Redis connection failed — cannot start in production: %s", exc)
            sys.exit(1)
        else:
            logger.warning(
                "Redis unavailable (%s). Running without queue support. "
                "Webhook ingest will fail at runtime.",
                exc,
            )
            app.state.redis = None

    # ── PostgreSQL ────────────────────────────────────────────────────────────
    try:
        await init_db()
        logger.info("PostgreSQL tables ready")
    except Exception as exc:
        if settings.ENVIRONMENT == "production":
            logger.critical("Database init failed — cannot start in production: %s", exc)
            sys.exit(1)
        else:
            logger.warning(
                "Database unavailable (%s). DB-dependent endpoints will return errors.",
                exc,
            )

    # ── Optional in-process ARQ worker (Render free tier mode) ───────────────
    # Set RUN_WORKER_INPROCESS=true to run the worker inside this process.
    # Use this when you can't afford a second service (e.g., Render free tier).
    if os.getenv("RUN_WORKER_INPROCESS", "").lower() in ("true", "1", "yes"):
        try:
            from arq import run_worker
            from app.worker import WorkerSettings
            logger.info("Starting in-process ARQ worker (RUN_WORKER_INPROCESS=true)")
            _worker_task = asyncio.create_task(
                run_worker(WorkerSettings, watch=False),
                name="arq-inprocess-worker",
            )
        except Exception as exc:
            logger.warning("Could not start in-process worker: %s", exc)

    yield  # ── Application is running ─────────────────────────────────────────

    # ── Shutdown ──────────────────────────────────────────────────────────────
    if _worker_task and not _worker_task.done():
        _worker_task.cancel()
        try:
            await _worker_task
        except asyncio.CancelledError:
            pass

    await close_redis_pool()
    await engine.dispose()
    logger.info("ALETHEIA shutdown complete")


app = FastAPI(
    title="ALETHEIA API",
    description=(
        "Autonomous AIOps platform for AI-driven incident detection and remediation. "
        "Receives monitoring alerts, generates code patches via Gemini AI, "
        "validates them with git dry-run, and creates GitHub PRs after human approval."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS ──────────────────────────────────────────────────────────────────────
_allowed_origins = [
    origin.strip()
    for origin in settings.FRONTEND_ORIGINS.split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["X-API-Key", "X-Hub-Signature-256", "X-Idempotency-Key", "Content-Type"],
)

# ── Routes ────────────────────────────────────────────────────────────────────
app.include_router(api_router, prefix="/api/v1")


# ── Health & readiness probes ─────────────────────────────────────────────────

@app.get("/health", tags=["Health"], summary="Liveness probe")
async def health_check() -> dict:
    """Returns 200 if the process is alive. Used by Docker/k8s liveness probes."""
    return {"status": "ok", "service": "ALETHEIA", "version": "1.0.0"}


@app.get("/ready", tags=["Health"], summary="Readiness probe")
async def readiness_check() -> dict:
    """Returns 200 if PostgreSQL is reachable. Used by Docker/k8s readiness probes."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database not ready: {exc}",
        )
    return {"status": "ready", "service": "ALETHEIA"}
