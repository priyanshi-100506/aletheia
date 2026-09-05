"""
Pytest configuration and shared fixtures for ALETHEIA.

Test isolation strategy:
    - The FastAPI app's lifespan is replaced with a no-op so tests
      don't require live PostgreSQL or Redis connections.
    - Redis-dependent functions (rate limiter, idempotency, queue) are
      overridden via FastAPI's `dependency_overrides` or `unittest.mock.patch`.
    - The ARQ queue call is patched at the module level in webhooks.py
      (where it was imported), not in the originating module.
    - Database session injection is overridden with an in-memory mock
      for endpoints that only need session-level operations.

Running the tests:
    uv run pytest tests/ -v
"""
import os
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Set test environment before any app imports resolve settings
os.environ["ENVIRONMENT"] = "development"
os.environ["DEMO_MODE"] = "true"
os.environ["API_KEY"] = ""
os.environ["WEBHOOK_SECRET"] = ""
os.environ["REDIS_URL"] = "redis://localhost:6379/0"  # Not actually connected in tests


@asynccontextmanager
async def _noop_lifespan(app):
    """No-op lifespan: skips Redis and PostgreSQL startup for unit tests."""
    app.state.redis = MagicMock()  # Stub so endpoints don't crash on app.state.redis
    yield


@pytest.fixture(scope="session")
def client():
    """Session-scoped TestClient with all external I/O mocked out.

    Patches applied:
      - App lifespan → no-op (no DB/Redis startup)
      - enqueue_remediation_job → async no-op (no real queue)
      - check_rate_limit → always True (no Redis)
      - check_idempotency_key → always True (no Redis)
    """
    from fastapi.testclient import TestClient
    import app.main as main_module

    # Replace lifespan before TestClient starts the app
    main_module.app.router.lifespan_context = _noop_lifespan

    with (
        patch("app.api.v1.endpoints.webhooks.enqueue_remediation_job", new_callable=AsyncMock) as _mock_enqueue,
        patch("app.api.v1.endpoints.webhooks.check_rate_limit", new_callable=AsyncMock, return_value=True),
        patch("app.api.v1.endpoints.webhooks.check_idempotency_key", new_callable=AsyncMock, return_value=True),
        patch("app.api.v1.endpoints.webhooks.AsyncSessionLocal") as mock_session_factory,
    ):
        # Make AsyncSessionLocal() usable as an async context manager
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session_factory.return_value = mock_session

        _mock_enqueue.return_value = "mock-job-id"

        with TestClient(main_module.app, raise_server_exceptions=True) as c:
            yield c
