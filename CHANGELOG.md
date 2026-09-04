# CHANGELOG

All notable changes to ALETHEIA are documented here.
Follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [1.0.0] — 2026-09-04 — v1 Production Freeze

### Added

**Queue (Redis + ARQ)**
- `app/services/queue_service.py` — ARQ enqueue wrapper with deterministic job IDs for idempotent re-enqueue
- `app/worker.py` — `WorkerSettings` class; run with `arq app.worker.WorkerSettings`
- `Dockerfile.worker` — dedicated ARQ worker container image
- Redis service added to `docker-compose.yml` with persistence (`appendonly yes`) and `maxmemory-policy allkeys-lru`

**Redis-backed security primitives**
- `app/services/redis_store.py` — Redis sliding-window rate limiter and atomic idempotency store, replacing in-memory dicts that were lost on restart and not shared across processes

**Infrastructure**
- `app/models/audit.py` + `app/models/remediation.py` now use `datetime.now(timezone.utc)` (fixes Python 3.12+ deprecation of `datetime.utcnow`)
- `WAIT_FOR_APPROVAL` status added to `PatchStatus` enum (previously the state was undocumented)
- `app/db/database.py` — connection pool tuned (`pool_size=10`, `max_overflow=20`, `pool_pre_ping=True`)
- `.env.example` — complete documented template for all environment variables
- `.dockerignore` — excludes `.venv`, `node_modules`, `.git`, `*.md`, `*.pyc`
- `Dockerfile.backend` rewritten to use `uv` and run as non-root `aletheia` user

**Documentation**
- `documentation.md` — complete v1 technical reference (12 sections, every module documented)
- `README.md` — rewritten with Docker quick-start, local dev guide, project structure
- `CHANGELOG.md` — this file

### Changed

**Orchestrator (`app/services/orchestrator.py`)**
- Each pipeline stage now opens and closes its own `AsyncSessionLocal()` session — eliminates session leaks on long-running AI/git operations
- `ctx: dict` parameter added as first argument (ARQ calling convention)
- Removed `asyncio.sleep(2**attempt)` backoff — ARQ's built-in retry handles this
- Removed in-process `asyncio.Semaphore` — ARQ `max_jobs` controls concurrency
- `_create_pr_for_job()` extracted as shared function for auto-approve and human-approval flows

**Patcher (`app/services/patcher.py`)**
- Removed "standalone mode" (silent DB error swallowing) — database is always required
- Clean error path: on Gemini failure, job status is set to FAILED before re-raising
- `GEMINI_MODEL` env var respected (was hardcoded to `gemini-3.6-flash`)

**Webhooks endpoint (`app/api/v1/endpoints/webhooks.py`)**
- Replaced `BackgroundTasks.add_task(process_remediation_job, ...)` with `enqueue_remediation_job(redis, ...)` (ARQ queue)
- Pre-creates `RemediationJob` row in PostgreSQL before enqueue, so `GET /jobs/{id}` works immediately
- Rate limiting and idempotency now use async Redis calls

**Approval endpoint (`app/api/v1/endpoints/approval.py`)**
- Replaced raw `AsyncSessionLocal()` usage with `Depends(get_db)` injection
- `list_activity` uses injected session instead of manual context manager

**Jobs endpoint (`app/api/v1/endpoints/jobs.py`)**
- `_serialize_job()` serializes datetimes to ISO 8601 strings (previously returned raw datetime objects that could fail JSON serialization in edge cases)
- Enum values serialized via `.value` to return plain strings

**main.py**
- Fail-fast in `ENVIRONMENT=production` if Redis or PostgreSQL is unreachable at startup (`sys.exit(1)`)
- Development mode logs a warning and continues, so you can develop without infrastructure
- `app.state.redis` set during startup for use by all endpoints
- Structured logging format configured globally

**docker-compose.yml**
- Added `redis` service (Redis 7 Alpine, persistent volume, health check)
- Added `worker` service (ARQ worker with same environment as backend)
- `backend` depends on both `postgres` (healthy) and `redis` (healthy)
- `worker` depends on both `postgres` (healthy) and `redis` (healthy)
- All services use `restart: unless-stopped`

### Fixed

- `datetime.utcnow()` deprecation in `RemediationJob` and `AuditLog` models
- Session leaks in `orchestrator.py` — sessions held across Gemini API calls (30-600s) were blocking connection pool slots
- In-memory rate limiter and idempotency store lost on every process restart
- `approval.py` used `AsyncSessionLocal()` directly instead of the session injected via `Depends(get_db)`, creating an extra unmanaged session per request
- `jobs.py` returned raw datetime objects from ORM — not always JSON-serializable
- `docker-compose.yml` missing Redis and worker services
- `Dockerfile.backend` used `requirements.txt` instead of `pyproject.toml`/`uv`

### Tests

- **12 tests** (up from 7), all passing
- `conftest.py` rebuilt with proper `patch()` targets in the module namespace where functions were imported
- `test_security_webhooks.py` — 5 tests covering health, ingest, Prometheus format, valid/invalid HMAC
- `test_webhook.py` — 7 tests covering normalization (3 formats) and orchestrator (4 code paths: happy-path, awaiting approval, generate failure, dry-run failure)
- Tests run in < 4 seconds with no live infrastructure required

### Breaking Changes

- Webhook ingest now requires Redis to be running (previously used FastAPI `BackgroundTasks` with no external dependency)
- `process_remediation_job` signature changed: first argument is now `ctx: dict` (ARQ worker context) — direct calls must pass `{}` as first argument
