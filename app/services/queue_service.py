"""
Queue service — thin ARQ enqueue wrapper.

The ingest endpoint calls `enqueue_remediation_job` to push a job into
the Redis-backed ARQ queue. The ARQ worker process (see `app/worker.py`)
picks it up and runs `process_remediation_job`.

Why this wrapper exists:
    - Decouples the endpoint from knowing about ARQ internals.
    - Makes it trivial to mock in tests (patch just this function).
    - Centralises queue configuration (queue name, job TTL, retry policy).
"""
import logging

import redis.asyncio as aioredis
from arq import ArqRedis
from arq.connections import RedisSettings

from app.config import settings

logger = logging.getLogger("aletheia")


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
        redis:        Active async Redis connection (from `app.state.redis`).
        job_id:       Pre-generated UUID for the RemediationJob row.
        error_log:    Normalized alert/error log text.
        target_file:  Path hint for the file to patch (empty string if unknown).
        auto_approve: Skip human approval gate if True.

    Returns:
        The ARQ job ID (distinct from the remediation job_id — it's the
        internal queue message identifier).
    """
    # Create an ARQ-capable Redis client from the existing connection pool.
    arq_redis = ArqRedis(pool_or_conn=redis)

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
        # arq returns None when a job with the same _job_id already exists
        logger.info("Job %s already enqueued (idempotent re-enqueue skipped)", job_id)
    else:
        logger.info("Job %s enqueued to ARQ queue", job_id)

    return job_id
