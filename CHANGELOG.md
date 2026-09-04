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
- In-process ARQ worker option (`RUN_WORKER_INPROCESS=true`) in `app/main.py` for $0 free-tier single-instance deployment on Render

**Security & Hardening**
- `app/services/patcher.py`: Added `_safe_read_target_file()` enforcing `Path.is_relative_to(repo_root)` and blocking sensitive files (`.env`, `id_rsa`, `*.pem`, `*.key`) from prompt context.
- `app/services/patcher.py`: Wrapped raw error logs and file context in strict XML tags (`<error_log>`, `<target_file>`) to eliminate prompt delimiter confusion.
- `app/api/v1/endpoints/patch.py`: Direct live modification locked down (`POST /patch/apply` with `dry_run=False` returns `403 Forbidden`). All live mutations strictly require the human approval workflow.
- `app/services/github_service.py` & `app/api/v1/endpoints/approval.py`: Added `_sanitize_output()` to redact Personal Access Tokens, GitHub tokens, and auth remote URLs from git errors, audit logs, and HTTP error responses.
- `app/services/orchestrator.py`: Added TOCTOU pre-approval dry-run verification against repository `HEAD` before opening PR branches.
- `app/services/redis_store.py`: Redis sliding-window rate limiter and atomic idempotency store, replacing in-memory dicts.

**Cloud Deployment & Infrastructure**
- `DEPLOY.md` — Step-by-step 100% Free-Tier Cloud Deployment Guide for Render (FastAPI + Worker), Neon (PostgreSQL), Upstash (Redis), and Vercel (React Frontend).
- `render.yaml` — Render Infrastructure-as-Code Blueprint.
- `frontend/vercel.json` — Vercel SPA rewrite and caching configuration.
- `app/db/database.py` — Auto-normalizes Neon connection strings (`sslmode=require` → `ssl=require`).
- `.gitignore` — Full protection for `.env`, `.venv`, `node_modules`, and cache directories.
- `.env.example` — Documented environment variables template.

**Documentation**
- `documentation.md` — Complete v1 technical reference (12 sections, every module documented).
- `README.md` — Architecture flow diagram, Docker quick-start, local dev guide, free-tier deployment, and webhook examples.
- `learnings.md` — Complete technical learning guide with first-principles breakdown and interview talking points.
- `handover.md` — Complete architecture handover reference.

### Changed

**Orchestrator (`app/services/orchestrator.py`)**
- Each pipeline stage opens and closes its own `AsyncSessionLocal()` session — eliminates session leaks on long-running AI/git operations.
- `ctx: dict` parameter added as first argument (ARQ calling convention).
- Concurrency managed via ARQ `max_jobs`.
- `_create_pr_for_job()` extracted as shared function for auto-approve and human-approval flows.

**Patcher (`app/services/patcher.py`)**
- Removed "standalone mode" (silent DB error swallowing) — database is always required.
- On Gemini failure, job status is set to `FAILED` before re-raising.
- `GEMINI_MODEL` defaults to `gemini-2.0-flash`.

**Webhooks endpoint (`app/api/v1/endpoints/webhooks.py`)**
- Replaced `BackgroundTasks` with `enqueue_remediation_job(redis, ...)` (ARQ queue).
- Pre-creates `RemediationJob` row in PostgreSQL before enqueue, so `GET /jobs/{id}` works immediately.
- Rate limiting and idempotency use async Redis calls.

**Approval endpoint (`app/api/v1/endpoints/approval.py`)**
- Uses `Depends(get_db)` injection.
- Re-verifies dry-run status and redacts tokens from all error outputs.

### Removed

- Deleted obsolete `app/services/rag.py` and `app/models/document.py` to eliminate code drift.

### Tests

- **16 tests**, 100% passing.
- `test_security_webhooks.py` — Health, ingest, Prometheus normalization, HMAC signatures, path traversal blocking, sensitive file filtering, token scrubbing, and /patch/apply direct mutation lockdown.
- `test_webhook.py` — Alert normalization (Generic, Prometheus, Datadog), orchestrator pipeline execution, auto-approve workflows, AI failure recovery, and dry-run validation error handling.
