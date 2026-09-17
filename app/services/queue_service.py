"""
Queue service — thin ARQ enqueue wrapper.

The ingest endpoint calls `enqueue_remediation_job` to push a job into
the Redis-backed ARQ queue. The ARQ worker process (see `app/worker.py`)
picks it up and runs `process_remediation_job`.
"""
import logging
from typing import Optional

import redis.asyncio as aioredis
try:
    from arq import ArqRedis, create_pool
    from arq.connections import RedisSettings
except ImportError:
    ArqRedis = None
    create_pool = None
    RedisSettings = None

from app.config import settings

logger = logging.getLogger("aletheia")

_arq_pool = None


def get_redis_settings() -> RedisSettings:
    """Parse the REDIS_URL into an ARQ `RedisSettings` object.

    ARQ does not accept a raw URL string — it requires a `RedisSettings`
    instance. This utility handles the conversion.
    """
    from urllib.parse import urlparse

    parsed = urlparse(settings.REDIS_URL)
    return RedisSettings(
        host=parsed.hostname or "127.0.0.1",
        port=parsed.port or 6379,
        database=int((parsed.path or "/0").lstrip("/") or 0),
        password=parsed.password,
    )


async def get_arq_redis() -> ArqRedis:
    """Get or create an ARQ Redis pool instance."""
    global _arq_pool
    if _arq_pool is None:
        _arq_pool = await create_pool(get_redis_settings())
    return _arq_pool


async def enqueue_remediation_job(
    redis: aioredis.Redis,
    job_id: str,
    error_log: str,
    target_file: str,
    *,
    auto_approve: bool = False,
) -> str:
    """Enqueue a remediation job into the ARQ Redis queue.

    Args:
        redis:        Active async Redis connection (or None).
        job_id:       Pre-generated UUID for the RemediationJob row.
        error_log:    Normalized alert/error log text.
        target_file:  Path hint for the file to patch (empty string if unknown).
        auto_approve: Skip human approval gate if True.

    Returns:
        The remediation job_id.
    """
    if isinstance(redis, ArqRedis):
        arq_redis = redis
    else:
        arq_redis = await get_arq_redis()

    arq_job = await arq_redis.enqueue_job(
        "process_remediation_job",   # Must match function name in WorkerSettings.functions
        job_id,
        error_log,
        target_file,
        auto_approve=auto_approve,
        _job_id=f"arq:{job_id}",     # Deterministic ARQ job ID → idempotent re-enqueue
        _expires=settings.REDIS_JOB_TTL,
    )

    if arq_job is None:
        logger.info("Job %s already enqueued (idempotent re-enqueue skipped)", job_id)
    else:
        logger.info("Job %s enqueued to ARQ queue", job_id)

    return job_id
