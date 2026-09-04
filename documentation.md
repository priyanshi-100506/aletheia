# ALETHEIA — Technical Architecture & v1 Reference

> **Version:** 1.0.0 — v1 Freeze  
> **Status:** Production-ready  
> Last updated: 2026-09-04

---

## Table of Contents

1. [What ALETHEIA Does](#1-what-aletheia-does)
2. [System Topology](#2-system-topology)
3. [Queue Architecture (Redis + ARQ)](#3-queue-architecture-redis--arq)
4. [Module Reference](#4-module-reference)
5. [Data Model](#5-data-model)
6. [API Reference](#6-api-reference)
7. [Configuration Reference](#7-configuration-reference)
8. [Security Architecture](#8-security-architecture)
9. [Frontend Architecture](#9-frontend-architecture)
10. [Deployment Guide](#10-deployment-guide)
11. [Development Guide](#11-development-guide)
12. [Decision Log](#12-decision-log)

---

## 1. What ALETHEIA Does

ALETHEIA is an autonomous AIOps platform. When your monitoring system fires an alert, ALETHEIA:

1. **Receives** the alert via a secure HTTP webhook
2. **Analyzes** the error log using Google Gemini AI with the actual source file as context
3. **Generates** a unified diff patch to fix the root cause
4. **Validates** the patch with `git apply --check` in an isolated temporary Git worktree
5. **Presents** the diff to an on-call engineer in the React UI for review
6. **Creates** a GitHub Pull Request after explicit human approval

No code is pushed without a human approving the diff. This is by design.

---

## 2. System Topology

```
External Monitoring (Datadog / Prometheus / Custom HTTP)
        │
        │ POST /api/v1/webhooks/ingest
        │ Headers: X-Hub-Signature-256, X-Idempotency-Key, X-API-Key
        ▼
┌─────────────────────────────────────────────┐
│  FastAPI API Server (port 8001)             │
│                                             │
│  1. Verify HMAC-SHA256 signature            │
│  2. Check Redis rate limit (30 req/min/IP)  │
│  3. Check Redis idempotency key (1h dedup)  │
│  4. Normalize alert payload                 │
│  5. Pre-create RemediationJob row in PG     │
│  6. Enqueue job_id → Redis (ARQ queue)      │
│  7. Return HTTP 202 { job_id }              │
└─────────────────────────────────────────────┘
        │
        │ Redis Queue (arq:queue)
        ▼
┌─────────────────────────────────────────────┐
│  ARQ Worker Process                         │
│                                             │
│  Stage 1: generate_patch()                  │
│    - Read target file from disk             │
│    - Call Gemini API (tenacity retry 4x)    │
│    - Store PatchResult in PostgreSQL        │
│    → Status: GENERATING → GENERATED        │
│                                             │
│  Stage 2: apply_unified_diff(dry_run=True)  │
│    - Run git apply --check in temp worktree │
│    → Status: DRY_RUN_PASSED                │
│                                             │
│  Stage 3: Await human approval              │
│    → Status: WAIT_FOR_APPROVAL             │
└─────────────────────────────────────────────┘
        │
        │ Engineer reviews diff in React UI
        │ POST /api/v1/jobs/{id}/approve
        ▼
┌─────────────────────────────────────────────┐
│  approve_and_create_pr()                    │
│                                             │
│  - Create git worktree at HEAD              │
│  - Apply patch to worktree                  │
│  - Commit: "fix(autofix): resolve {id}"     │
│  - Push branch: fix/aletheia-{job_id}       │
│  - POST https://api.github.com/repos/.../   │
│    pulls → GitHub Pull Request              │
│  → Status: PR_CREATED                      │
└─────────────────────────────────────────────┘
```

---

## 3. Queue Architecture (Redis + ARQ)

### Why ARQ over Celery or RabbitMQ

| Concern | Celery | RabbitMQ | ARQ (chosen) |
|---------|--------|----------|--------------|
| Async-native | No (requires `gevent` or `eventlet`) | No | **Yes** — `async def` tasks natively |
| Dependencies | `celery`, `kombu`, `billiard` | `pika` or `aio-pika` | `arq`, `redis` only |
| Broker setup | Separate RabbitMQ or Redis config | RabbitMQ server | **Redis** (already required) |
| Result storage | Redis/DB optional | Needs separate result backend | **Redis** built-in |
| Retry policy | `max_retries`, `countdown` | DLQ config | **`max_tries`, `retry_sleep`** |

ARQ is async-native. Since every ALETHEIA service function is already `async def`, ARQ integrates with zero adapter code.

### Queue Flow

```
API Server                    Redis                    ARQ Worker
    │                           │                           │
    │──enqueue_job(job_id)──→   │  arq:queue  ─────────→   │
    │                           │                           │ process_remediation_job(ctx, job_id, ...)
    │                           │                           │
    │  GET /jobs/{job_id}  ←─── │ ←── job result stored ───│
```

### Job Deduplication

Each ARQ job is enqueued with `_job_id=f"arq:{job_id}"`. If the same job_id is enqueued twice (e.g., duplicate webhook), ARQ silently skips the second enqueue — no duplicate work runs.

### Worker Configuration (`app/worker.py` → `WorkerSettings`)

| Setting | Default | Meaning |
|---------|---------|---------|
| `max_jobs` | `4` | Concurrent jobs per worker process |
| `max_tries` | `3` | Total attempts (1 initial + 2 retries) |
| `job_timeout` | `600s` | Max time for one job execution (10 min) |
| `keep_result` | `86400s` | How long job result stays in Redis (24h) |

---

## 4. Module Reference

### `app/main.py`
FastAPI application factory. Manages the `lifespan` context:
- Connects to Redis on startup via `init_redis_pool()`; stores pool as `app.state.redis`
- Calls `init_db()` to create PostgreSQL tables if they don't exist
- In `ENVIRONMENT=production`, calls `sys.exit(1)` if either Redis or PostgreSQL is unreachable
- Mounts CORS middleware and the v1 API router

### `app/config.py`
Single source of truth for all configuration. Uses `pydantic-settings` to read from environment variables and `.env` file. See [Configuration Reference](#7-configuration-reference) for all variables.

### `app/db/database.py`
- `engine` — SQLAlchemy async engine with connection pool (`pool_size=10`, `max_overflow=20`, `pool_pre_ping=True`)
- `AsyncSessionLocal` — async session factory
- `init_db()` — creates all tables at startup (not a migration tool)
- `get_db()` — FastAPI dependency yielding an `AsyncSession`

### `app/models/remediation.py`
`RemediationJob` ORM model. Tracks every remediation attempt from alert receipt through PR creation.

**PatchStatus enum lifecycle:**
```
PENDING → GENERATING → GENERATED → DRY_RUN_PASSED → WAIT_FOR_APPROVAL
                                                   → PR_CREATED (auto-approve)
Any state → FAILED (on error)
PR_CREATED → APPLIED (after merge, set manually or via webhook)
```

### `app/models/audit.py`
`AuditLog` — append-only audit trail. Never delete rows. One row per significant event. Used by the React Activity Log screen.

**Standard event_type values:**
`WEBHOOK_INGESTED`, `PIPELINE_STARTED`, `PATCH_GENERATED`, `DRY_RUN_PASSED`,
`AWAITING_APPROVAL`, `APPROVAL_GRANTED`, `REJECTED`, `PR_CREATED`, `PIPELINE_FAILED`

### `app/schemas/webhook.py`
Alert payload normalization. Maps 3 provider formats to `GenericAlertPayload(error_log, target_file)`:
- **Generic:** `{"error_log": "...", "target_file": "..."}` — passed through directly
- **Prometheus Alertmanager:** extracts `annotations.description` from firing alerts
- **Datadog:** extracts `message` or `body` field

### `app/schemas/patch.py`
`PatchResult` — Pydantic model used as Gemini's structured output schema. Contains `file_path`, `bug_description`, `explanation`, `unified_diff`, `confidence_score`.

### `app/services/orchestrator.py`
The core pipeline. Runs inside the ARQ worker, not inside FastAPI. Key design decisions:
- **Each stage opens/closes its own DB session** — no session objects are passed between functions, preventing detached-instance errors
- **`_record_audit()` never raises** — audit logging failures are logged but never interrupt the pipeline
- **`auto_approve=False` by default** — safety gate; PR creation requires explicit human approval

### `app/services/patcher.py`
Gemini AI integration. Builds a structured prompt from the error log and source file content, calls `generate_content` with `response_schema=PatchResult` for guaranteed structured JSON output. Uses `tenacity` for retry on transient errors (429, 503, 500).

### `app/services/git_applier.py`
Git patch validation and application:
- `sanitize_diff()` — strips markdown code fences, normalizes line endings
- `_validate_diff_paths()` — rejects patches with absolute paths or `..` traversal
- `_repository_path()` — ensures repo path is within the configured `REPO_PATH` boundary
- `apply_unified_diff(dry_run=True)` — runs `git apply --check --recount --ignore-whitespace`

### `app/services/github_service.py`
Pull request creation:
1. Creates a temporary Git worktree at `HEAD` (isolates from working directory)
2. Creates branch `fix/aletheia-{job_id}`
3. Applies patch with `git apply -`
4. Commits and pushes to `origin` with embedded PAT in HTTPS URL
5. Calls `POST https://api.github.com/repos/{owner}/{repo}/pulls`
6. Cleans up worktree

If `GITHUB_TOKEN` is not set, returns a simulated response for local development.

### `app/services/security_service.py`
HMAC-SHA256 webhook signature verification. Stateless. Accepts `sha256=<hex>` prefix format (GitHub/Datadog style) or raw hex. Returns `True` if `WEBHOOK_SECRET` is unset (dev mode).

### `app/services/redis_store.py`
Redis-backed rate limiter and idempotency store. Replaces the previous in-memory dicts which were lost on restart and not shared across processes.

**Rate limiting algorithm:** Sliding-window sorted set. Each request's timestamp is added as a member; old timestamps are pruned on each request. Atomic pipeline to count + add + expire.

**Idempotency:** `SET NX EX` — atomic check-and-set. Returns `True` (fresh) if key was set, `False` (duplicate) if key already existed.

### `app/services/queue_service.py`
Thin ARQ enqueue wrapper. The ingest endpoint calls `enqueue_remediation_job()` instead of knowing about ARQ internals. Handles `REDIS_URL → RedisSettings` parsing.

### `app/worker.py`
ARQ `WorkerSettings` class. Entry point for the worker process:
```bash
arq app.worker.WorkerSettings
```

### `app/security.py`
`require_api_key` — FastAPI dependency. In development mode with no `API_KEY` set, passes all requests. In production, requires `X-API-Key` header to match `settings.API_KEY`.

---

## 5. Data Model

### `remediation_jobs`

| Column | Type | Notes |
|--------|------|-------|
| `id` | VARCHAR(36) PK | UUID string |
| `error_log` | TEXT | Raw alert text |
| `target_file` | VARCHAR(512) | File path hint |
| `bug_description` | TEXT | AI-generated description |
| `explanation` | TEXT | AI-generated fix explanation |
| `unified_diff` | TEXT | The actual patch |
| `confidence_score` | FLOAT | 0.0 – 1.0 |
| `status` | ENUM | PatchStatus lifecycle state |
| `error_message` | TEXT | Failure reason (if FAILED) |
| `created_at` | TIMESTAMPTZ | UTC, timezone-aware |
| `updated_at` | TIMESTAMPTZ | UTC, updated on every write |

### `audit_logs`

| Column | Type | Notes |
|--------|------|-------|
| `id` | VARCHAR(36) PK | UUID string |
| `job_id` | VARCHAR(36) | FK to remediation_jobs (not enforced) |
| `event_type` | VARCHAR(64) | Screaming snake case constant |
| `actor` | VARCHAR(128) | "system" or engineer username |
| `details` | JSON | Event-specific payload |
| `created_at` | TIMESTAMPTZ | UTC, never updated |

---

## 6. API Reference

All endpoints are under `/api/v1`. All require `X-API-Key` header unless `ENVIRONMENT=development` and `API_KEY` is unset.

### Webhooks
| Method | Path | Description |
|--------|------|-------------|
| POST | `/webhooks/ingest` | Receive alert, enqueue remediation job → 202 |

### Jobs
| Method | Path | Description |
|--------|------|-------------|
| GET | `/jobs` | List jobs, newest first (`?limit=50`) |
| GET | `/jobs/{job_id}` | Get single job detail + diff |

### Approval
| Method | Path | Description |
|--------|------|-------------|
| POST | `/jobs/{job_id}/approve` | Approve patch → create GitHub PR |
| POST | `/jobs/{job_id}/reject` | Reject patch → mark FAILED |
| GET | `/activity` | Audit log stream (`?limit=50`) |

### Patch (dry-run & sync generation)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/patch/generate` | Generate patch synchronously |
| POST | `/patch/apply` | Validate patch diff (`dry_run=true` only; `dry_run=false` returns 403) |

### Health
| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness probe → 200 always |
| GET | `/ready` | Readiness probe → 200 if DB reachable |

---

## 7. Configuration Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | postgres@localhost:5435 | Async PostgreSQL connection string (Neon compatible) |
| `GEMINI_API_KEY` | Yes | — | Google AI Studio API key |
| `GEMINI_MODEL` | No | `gemini-2.0-flash` | Model name override |
| `GITHUB_TOKEN` | No* | — | PAT for PR creation (* required for real PRs) |
| `GITHUB_REPOSITORY` | No | — | `owner/repo` for PR target |
| `GITHUB_BASE_BRANCH` | No | `main` | Base branch for PRs |
| `REPO_PATH` | No | `.` | Absolute path to local git checkout |
| `API_KEY` | No* | — | API key for endpoint auth (* required in production) |
| `WEBHOOK_SECRET` | No* | — | HMAC secret for webhook validation |
| `REDIS_URL` | Yes | redis://localhost:6379/0 | Redis connection URL (Upstash compatible) |
| `WORKER_CONCURRENCY` | No | `4` | ARQ concurrent jobs per worker |
| `REDIS_JOB_TTL` | No | `86400` | Seconds before job expires from queue |
| `RATE_LIMIT_MAX_REQUESTS` | No | `30` | Max webhook requests per IP per window |
| `RATE_LIMIT_WINDOW_SECONDS` | No | `60` | Rate limit sliding window size |
| `IDEMPOTENCY_TTL_SECONDS` | No | `3600` | Idempotency key dedup window |
| `MAX_PATCH_LENGTH` | No | `500000` | Maximum allowed patch size in bytes |
| `RUN_WORKER_INPROCESS` | No | `false` | Run ARQ worker inside FastAPI lifespan (for Render free tier) |
| `ENVIRONMENT` | No | `development` | `development` or `production` |
| `FRONTEND_ORIGINS` | No | localhost:5174 | Comma-separated CORS allowed origins |

---

## 8. Security Architecture

### 1. HMAC Webhook Signature Verification
Every inbound webhook is validated against `WEBHOOK_SECRET` using HMAC-SHA256 before any processing occurs. Invalid signatures return HTTP 401. This prevents spoofed alerts from triggering AI-driven code changes.

### 2. Redis Rate Limiting
Sliding-window rate limiter per client IP using Redis sorted sets. Default: 30 requests per 60-second window. Returns HTTP 429 on excess. Persists across restarts and works correctly with multiple API server replicas.

### 3. Idempotency Deduplication
`X-Idempotency-Key` header deduplication using Redis `SET NX EX`. Prevents the same alert from triggering multiple parallel remediation jobs. Returns HTTP 409 on duplicate.

### 4. Path Traversal & Sensitive File Filtering (`_safe_read_target_file`)
Target file paths in alert payloads are verified with `Path.is_relative_to(repo_root)`. Traversal attacks (`../../etc/passwd`) and sensitive files (`.env`, `.env.*`, `id_rsa`, `*.pem`, `*.key`) are strictly blocked from being read into LLM prompts.

### 5. Prompt Delimitation & Injection Protection
All error logs and file context are encapsulated in strict XML tags (`<error_log>`, `<target_file>`) to prevent prompt confusion or injection attacks.

### 6. Strict Direct Apply Lockdown
`POST /api/v1/patch/apply` prohibits direct live modification (`dry_run=False` returns `403 Forbidden`). All live mutations are strictly constrained to the approval-gated PR workflow.

### 7. Credential & PAT Scrubbing
All git errors and GitHub API exception strings pass through `_sanitize_output()`, which redacts Personal Access Tokens, Bearer headers, and authenticated remote URLs before writing to audit logs or returning HTTP responses.

### 8. TOCTOU Race Condition Prevention
Before creating PR branches upon human approval, `approve_and_create_pr()` performs a dry-run re-verification against current repository `HEAD`. If the codebase has diverged since generation, the job fails gracefully rather than applying a conflicting patch.

### 9. Git Worktree Isolation
All patch application (dry-run and real) happens in a temporary `git worktree` — a separate directory linked to the same repo object. The primary working directory is never modified. Worktrees are always cleaned up in a `finally` block.

### 10. Append-Only Audit Trail
`audit_logs` table is written to but never updated or deleted. Every security event, approval, and rejection is permanently recorded with timestamp, actor, and structured details.

---

## 9. Frontend Architecture

The React frontend (`frontend/`) is the operational command center for on-call engineers. Built with React + TypeScript + Vite, styled with the **Orchid Noir** design system.

### Screens

| Screen | Component | Purpose |
|--------|-----------|---------|
| Incident Command Center | `App.tsx` (main view) | Live job table, status badges, filter bar |
| Diff Viewer | `DiffViewer.tsx` | Split/unified diff with approve/reject controls |
| Activity Log | `ActivityLog.tsx` | Real-time audit event stream |
| Repositories | `Repositories.tsx` | Active repo connections, worktree status |
| Settings / Ingest | `Settings.tsx`, `AlertIngestModal.tsx` | Config display, manual alert trigger |

### API Client (`api.ts`)

All backend calls go through `api.ts`. The base URL is configurable via `VITE_API_URL` environment variable (defaults to `http://localhost:8001`).

### Development
```bash
cd frontend
npm install
npm run dev   # starts at http://localhost:5174
```

---

## 10. Deployment Guide

### Prerequisites
- Docker & Docker Compose v2+
- `.env` file (copy from `.env.example` and fill in values)

### One-command startup
```bash
cp .env.example .env
# Edit .env: add GEMINI_API_KEY, GITHUB_TOKEN, API_KEY, WEBHOOK_SECRET
docker compose up --build
```

This starts 5 services:
| Service | Port | Role |
|---------|------|------|
| `postgres` | 5435 | PostgreSQL 16 + pgvector |
| `redis` | 6379 | Queue broker + rate limiter |
| `backend` | 8001 | FastAPI API server |
| `worker` | — | ARQ remediation pipeline worker |
| `frontend` | 5174 | React UI (nginx) |

### Service URLs
- API docs: http://localhost:8001/docs
- Health: http://localhost:8001/health
- Readiness: http://localhost:8001/ready
- Frontend: http://localhost:5174

### Development (local, without Docker)

**Terminal 1 — PostgreSQL + Redis:**
```bash
docker compose up postgres redis
```

**Terminal 2 — FastAPI backend:**
```bash
uv run uvicorn app.main:app --reload --port 8001
```

**Terminal 3 — ARQ worker:**
```bash
uv run arq app.worker.WorkerSettings
```

**Terminal 4 — React frontend:**
```bash
cd frontend && npm run dev
```

### Sending a test webhook

```bash
curl -X POST http://localhost:8001/api/v1/webhooks/ingest \
  -H "Content-Type: application/json" \
  -d '{"error_log": "AttributeError: NoneType has no attribute get", "target_file": "transaction_service.py"}'
```

---

## 11. Development Guide

### Running Tests
```bash
uv run pytest tests/ -v
```

Tests do NOT require live PostgreSQL or Redis. All external I/O is mocked via `tests/conftest.py`.

### Test Coverage by File (16/16 Passing)
| Test file | What it covers |
|-----------|---------------|
| `test_security_webhooks.py` | Health probe, 202 acceptance, Prometheus payloads, HMAC valid/invalid verification, path traversal blocking, sensitive file blocking, token scrubbing, and /patch/apply direct mutation denial (403). |
| `test_webhook.py` | Alert normalization (Generic, Prometheus, Datadog), orchestrator pipeline execution, auto-approve workflows, AI generation failure recovery, and dry-run validation error handling. |

### Adding a New Service

1. Create `app/services/my_service.py` with `async def my_function(...):`
2. Add docstring explaining: what it does, session contract, what it raises
3. If it needs to run as a background job, add it to `WorkerSettings.functions` in `app/worker.py`
4. Add tests in `tests/test_my_service.py` with all external calls mocked

### Environment Variables in Tests

`tests/conftest.py` sets `ENVIRONMENT=development` and `API_KEY=""` before any imports. This bypasses API key enforcement. Do not use production credentials in tests.

---

## 12. Decision Log

| Decision | Chosen | Rejected alternatives | Reason |
|----------|--------|----------------------|--------|
| Queue | **ARQ + Redis** | Celery, RabbitMQ | ARQ is async-native; our codebase is entirely `async def`; Celery requires sync task bodies or complex workarounds; RabbitMQ adds ops complexity |
| AI model | **Gemini 2.0 Flash** | GPT-4, Claude | Structured JSON output via `response_schema` is first-class; fast and cheap |
| Retry library | **tenacity** | Manual retry loop | Declarative, composable, handles exponential backoff cleanly |
| DB ORM | **SQLAlchemy async** | raw asyncpg, tortoise-orm | Mature ecosystem, typed mapped columns, async-native in v2 |
| Session pattern | **Per-operation sessions** | Single long-lived session | Avoids connection leaks across long AI/git operations; async context manager ensures cleanup |
| Rate limiting | **Redis sorted set** | In-memory dict | Survives restarts; shared across replicas; O(log n) sliding window |
| Patch validation | **git apply --check** | applying to temp copy | Uses the actual git conflict detection algorithm; handles 3-way merge |
| PR isolation | **git worktree** | temp clone | Same repo object (fast); primary working directory untouched; native git feature |
| Approval gate | **Server-side endpoint** | Frontend-only | Cannot be bypassed by manipulating the React UI; full audit trail |
