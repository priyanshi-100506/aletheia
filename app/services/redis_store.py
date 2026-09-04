"""
Redis-backed rate limiter and idempotency store.

Replaces the previous module-level in-memory dicts, which were:
  1. Lost on every process restart
  2. Not shared across multiple worker processes
  3. Not shared across multiple API server replicas

All operations use a single shared Redis connection pool managed by the
caller (see `app/main.py` lifespan for pool lifecycle).

Rate limiting algorithm: Sliding-window counter backed by a Redis sorted set.
Each client IP gets a key `ratelimit:{ip}`. Timestamps of requests in the
current window are stored as members, allowing O(log n) cleanup and count.

Idempotency: Each processed key is stored as `idempotency:{key}` with a TTL.
"""
import logging
import time

import redis.asyncio as aioredis

from app.config import settings

logger = logging.getLogger("aletheia")

# Module-level pool, initialised by `init_redis_pool()` at app startup.
_redis_pool: aioredis.Redis | None = None


async def init_redis_pool() -> aioredis.Redis:
    """Create and return the shared async Redis connection pool.

    Should be called once during application lifespan startup and stored
    in `app.state.redis` for sharing across requests.
    """
    global _redis_pool
    _redis_pool = aioredis.from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
        max_connections=20,
    )
    # Verify connectivity
    await _redis_pool.ping()
    logger.info("Redis connection established: %s", settings.REDIS_URL)
    return _redis_pool


async def close_redis_pool() -> None:
    """Close the Redis connection pool at application shutdown."""
    global _redis_pool
    if _redis_pool:
        await _redis_pool.aclose()
        _redis_pool = None


def _get_pool() -> aioredis.Redis:
    """Return the active pool or raise if not initialised."""
    if _redis_pool is None:
        raise RuntimeError(
            "Redis pool is not initialised. "
            "Call `init_redis_pool()` during application startup."
        )
    return _redis_pool


async def check_rate_limit(client_id: str) -> bool:
    """Sliding-window rate limiter.

    Args:
        client_id: Typically the client IP address.

    Returns:
        True  — request is allowed.
        False — client has exceeded the allowed rate.
    """
    redis = _get_pool()
    key = f"ratelimit:{client_id}"
    now = time.time()
    window_start = now - settings.RATE_LIMIT_WINDOW_SECONDS

    pipe = redis.pipeline()
    # Remove timestamps older than the current window
    pipe.zremrangebyscore(key, "-inf", window_start)
    # Count remaining requests in the window
    pipe.zcard(key)
    # Add current request timestamp
    pipe.zadd(key, {str(now): now})
    # Reset TTL so the key expires naturally after the window
    pipe.expire(key, settings.RATE_LIMIT_WINDOW_SECONDS + 1)
    results = await pipe.execute()

    current_count: int = results[1]
    if current_count >= settings.RATE_LIMIT_MAX_REQUESTS:
        logger.warning("Rate limit exceeded for client: %s", client_id)
        return False
    return True


async def check_idempotency_key(idempotency_key: str) -> bool:
    """Check whether an idempotency key has been processed recently.

    Args:
        idempotency_key: Arbitrary string from the `X-Idempotency-Key` header.

    Returns:
        True  — key is fresh; caller should proceed with processing.
        False — key was seen recently; caller should return 409 Conflict.
    """
    redis = _get_pool()
    key = f"idempotency:{idempotency_key}"

    # SET NX (only if not exists) with TTL
    stored = await redis.set(key, "1", nx=True, ex=settings.IDEMPOTENCY_TTL_SECONDS)
    if stored is None:
        # Key already existed — duplicate request
        logger.info("Duplicate idempotency key rejected: %s", idempotency_key)
        return False
    return True
