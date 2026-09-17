"""
ARQ worker entry point.

Run this process alongside the FastAPI server:
    arq app.worker.WorkerSettings

Or via Docker Compose (see docker-compose.yml `worker` service).

The worker connects to Redis, dequeues jobs, and runs the remediation
pipeline asynchronously. ARQ handles:
  - Durable job persistence (survives API server restarts)
  - Automatic retries on failure (configured below)
  - Concurrency limiting
  - Job result storage in Redis

Configuring retries:
    `max_tries` — total attempts before giving up (including first attempt).
    `retry_sleep` — base seconds between attempts (ARQ uses exponential backoff).

Adding new job functions:
    1. Define `async def my_task(ctx: dict, ...) -> dict` in a service module.
    2. Add it to `WorkerSettings.functions` list below.
    3. The function name string (e.g. "my_task") is used by `enqueue_job(...)`.
"""
import logging
import os

from arq.connections import RedisSettings
from dotenv import load_dotenv

load_dotenv()

from app.services.orchestrator import process_remediation_job
from app.services.queue_service import get_redis_settings

logger = logging.getLogger("aletheia")


async def startup(ctx: dict) -> None:
    """Called once when the worker process starts.

    Sets up any shared resources (DB engine, HTTP clients) that should be
    reused across jobs rather than recreated per job.
    """
    logger.info("ARQ worker starting up (pid=%s)", os.getpid())
    # Database sessions are created per-job inside orchestrator.py
    # to avoid holding connections open between jobs.


async def shutdown(ctx: dict) -> None:
    """Called once when the worker process shuts down cleanly."""
    logger.info("ARQ worker shutting down")


class WorkerSettings:
    """ARQ worker configuration.

    ARQ reads this class by convention when you run:
        arq app.worker.WorkerSettings
    """

    # Which async functions this worker can execute.
    # The string used in `enqueue_job("process_remediation_job", ...)` must
    # match the function's __name__.
    functions = [process_remediation_job]

    # Redis connection settings (parsed from REDIS_URL in config)
    redis_settings: RedisSettings = get_redis_settings()

    # Lifecycle hooks
    on_startup = startup
    on_shutdown = shutdown

    # Maximum number of jobs running concurrently in this worker process.
    # Set to a low number because each job makes external API calls (Gemini, GitHub).
    max_jobs: int = int(os.getenv("WORKER_CONCURRENCY", "4"))

    # Total attempts per job (1 initial + N retries)
    max_tries: int = 3

    # Seconds before a queued job is considered expired and dropped.
    # Default: 24 hours. Prevents stale alerts from being processed long after
    # the incident has been resolved manually.
    job_timeout: int = 600   # 10 minutes per job execution
    keep_result: int = 86_400  # Keep result in Redis for 24 hours

    # Queue name — must match the queue the API server enqueues to.
    queue_name: str = "arq:queue"
