# ALETHEIA Backend Engineering Learning Guide

## Purpose

Learn the backend engineering concepts needed to explain, debug, modify, and defend ALETHEIA without relying on an AI agent. This guide uses the repository as the source of truth.

The most important distinction to keep in mind:

> ALETHEIA has a real alert-to-patch-to-PR workflow. Its portfolio runner now proves constrained patch application and targeted tests in isolated fixture repositories without external AI or GitHub calls. Full migration management, durable queue recovery, metrics, and production-grade recovery semantics remain **NOT IMPLEMENTED**.

## How To Study This Guide

For each topic:

1. Learn the general concept.
2. Open the listed files and trace the named function.
3. Explain the failure case aloud.
4. Only then consider changing code.

---

## A. Python Backend Fundamentals

### 1. Application Structure

**Concept**

A backend application is divided into modules that own different responsibilities.

**Why it exists**

Without separation, HTTP handling, business logic, persistence, queueing, and external APIs become one tangled program.

**Simple explanation**

ALETHEIA is a Python package:

```text
app/
├── main.py              Application entry point
├── config.py            Configuration
├── security.py          API authentication
├── api/                 HTTP routes
├── schemas/             Input/output validation
├── models/              Database models
├── db/                  Database setup
├── services/            Business and integration logic
└── worker.py            ARQ worker configuration
```

**How it works internally**

Python imports modules. A module is a `.py` file. A package is a directory containing Python modules, usually with `__init__.py`.

The import graph is roughly:

```text
main.py
 ├── config.py
 ├── db.database
 ├── api.v1.router
 └── service initialization

API endpoints
 ├── schemas
 ├── services
 ├── database
 └── security

worker.py
 └── orchestrator.py
      ├── patcher.py
      ├── git_applier.py
      └── github_service.py
```

**How ALETHEIA uses it**

The endpoint modules should receive requests and delegate work. The service modules perform business operations. The models represent database state.

**Exact files/functions**

- `app/main.py`: `app`, `lifespan`
- `app/api/v1/router.py`
- `app/services/orchestrator.py`: `process_remediation_job`
- `app/services/patcher.py`

**Example**

`ingest_alert()` receives a webhook, normalizes it, persists a `RemediationJob`, and enqueues work. It should not itself contain Gemini prompt construction or Git commands.

**Failure case**

If a service is duplicated or bypassed, different endpoints can implement inconsistent state transitions.

ALETHEIA has this issue partially:

- `app/db/database.py` is the active database module.
- `app/services/database.py` defines another database setup but is not used.
- `scripts/seed_context.py` imports a missing RAG module.

**How to debug it**

Search for:

```text
from app.services.database
from app.db.database
```

Then identify which module `main.py`, endpoints, and workers actually import.

**Interview question**

Why should an HTTP endpoint not directly contain GitHub, SQL, and LLM logic?

**Remember**

A module boundary is useful only when the boundary reflects ownership and is actually respected.

### 2. Configuration and Environment Variables

**Concept**

Configuration is the set of values that change between environments without changing source code.

**Why it exists**

Development, testing, staging, and production need different database URLs, API keys, model names, and service endpoints.

**How it works internally**

Configuration values are read when the application starts. Defaults are applied when variables are absent. Sensitive values should come from the environment rather than source code.

**How ALETHEIA uses it**

Examples include:

- `DATABASE_URL`
- `REDIS_URL`
- `GEMINI_API_KEY`
- `GEMINI_MODEL`
- `GITHUB_TOKEN`
- `API_KEY`
- `WEBHOOK_SECRET`
- `REPO_PATH`
- `RUN_WORKER_INPROCESS`

**Exact files/functions**

- `app/config.py`: `Settings`
- `.env.example`
- `docker-compose.yml`
- `render.yaml`

**Example**

`GEMINI_MODEL` has inconsistent defaults:

- `app/config.py` defaults to `gemini-3.6-flash`.
- Docker and Render configuration use `gemini-2.0-flash`.

**Failure case**

A developer may believe the system is using one model while deployment uses another.

**How to debug it**

Inspect:

1. `Settings` defaults.
2. Docker environment variables.
3. Render environment variables.
4. Runtime startup logs.

Never print secret values.

**Interview question**

Why should production configuration fail at startup when a required secret is missing?

**Remember**

A default is not automatically safe. Defaults for security-sensitive settings should usually fail closed.

### 3. Pydantic and Type Validation

**Concept**

Pydantic converts and validates untrusted data against declared schemas.

**Why it exists**

HTTP JSON is untrusted. Python type hints alone do not validate runtime input.

**Simple explanation**

A Pydantic model defines the shape and rules for a request or response.

**How it works internally**

FastAPI parses JSON, constructs a Pydantic model, and returns a validation error if the data does not match.

**How ALETHEIA uses it**

Examples:

- `PatchResult`
- webhook payload models
- patch request models
- approval request models

**Exact files**

- `app/schemas/patch.py`
- `app/schemas/webhook.py`
- `app/schemas/api.py`
- `app/models/remediation.py`

**Example**

`PatchResult` requires:

```text
file_path
explanation
bug_description
unified_diff
confidence_score
```

**Failure case**

A schema can verify that a field exists without verifying that its value is safe or meaningful.

`confidence_score` has no effective enforcement of the documented `0.0–1.0` range. A structurally valid diff can still be semantically wrong.

**How to debug it**

Send malformed and boundary inputs through the endpoint and inspect the validation response. Then inspect whether the value is validated again before being used by Git.

**Interview question**

What is the difference between structural validation and semantic validation?

**Remember**

Pydantic can tell you “this is shaped like a patch result.” It cannot tell you “this patch fixes the incident safely.”

### 4. Async/Await and Coroutines

**Concept**

`async def` functions can pause while waiting for I/O, allowing another task to run.

**Why it exists**

Network and database operations are slow compared with CPU operations. Blocking the event loop reduces throughput.

**Simple explanation**

An async function is not automatically running in parallel. It cooperatively gives control back when it awaits.

**How it works internally**

An event loop schedules coroutines. When a coroutine reaches `await`, it can suspend until its I/O operation completes.

**How ALETHEIA uses it**

Async operations include:

- FastAPI route handlers
- SQLAlchemy async sessions
- Redis operations
- ARQ jobs
- HTTP calls with `httpx.AsyncClient`

Blocking work is moved to a thread:

```python
await asyncio.to_thread(...)
```

**Exact files**

- `app/main.py`
- `app/db/database.py`
- `app/services/patcher.py`
- `app/services/git_applier.py`
- `app/services/orchestrator.py`

**Example**

The Gemini SDK call is synchronous, so `_call_gemini_sync()` is run through a worker thread.

**Failure case**

Calling blocking Git or SDK code directly inside an async route can freeze the event loop.

**How to debug it**

Look for synchronous functions called from `async def`. Check whether they are:

- Awaited asynchronous calls.
- Sent to `asyncio.to_thread`.
- Short CPU-only operations.
- Potentially blocking subprocess or network calls.

**Interview question**

Does `async def` make CPU-heavy code faster?

**Remember**

Async improves I/O concurrency. It does not make CPU work disappear.

### 5. Exception Handling and Logging

**Concept**

Exceptions represent failures. Logging records enough context to diagnose them.

**Why it exists**

Production systems must distinguish expected client errors, retryable dependency failures, permanent validation failures, and unknown defects.

**How ALETHEIA uses it**

The orchestrator catches failures and changes jobs to `FAILED`. Services log failures. Audit records are written through `_record_audit()`.

**Exact files**

- `app/services/orchestrator.py`
- `app/main.py`
- `app/services/github_service.py`
- `app/services/patcher.py`

**Failure case**

The worker catches generation and dry-run exceptions and returns a failure dictionary. Because it returns normally, ARQ may not see an exception and therefore may not retry the job despite `max_tries=3`.

**How to debug it**

Trace:

```text
exception raised
→ caught where?
→ status changed?
→ exception re-raised?
→ task returned normally?
```

**Remember**

A retry configuration is meaningless if application code catches the exception before the queue sees it.

---

## B. FastAPI

### 1. Application Initialization

**Concept**

Application initialization assembles routes, middleware, configuration, resources, and lifecycle hooks.

**ALETHEIA implementation**

`app/main.py` creates the FastAPI application, mounts the versioned router, and uses a lifespan function to initialize and close resources.

```text
FastAPI
 ├── /health
 ├── /ready
 └── /api/v1
```

**Why**

The application object is the root of the HTTP server.

**Failure**

If startup initializes database or Redis incorrectly, the API can start in a partially usable state.

**Debug**

Inspect startup logs and the `lifespan` function. Compare `/health` and `/ready`.

**Remember**

Liveness asks “is the process alive?” Readiness asks “can it serve useful traffic?”

### 2. Routers and Endpoints

**Concept**

Routers group related HTTP endpoints.

**ALETHEIA implementation**

- `webhooks.py`: alert ingestion
- `jobs.py`: querying jobs
- `approval.py`: approval, rejection, activity
- `patch.py`: direct patch operations

Mounted by:

- `app/api/v1/router.py`

**Request path**

```text
POST /api/v1/webhooks/ingest
→ FastAPI route matching
→ dependency execution
→ body parsing
→ endpoint function
```

**Failure**

There is also an obsolete unmounted router in `app/routers/webhooks.py`. Reading it may create a false understanding of live behavior.

**Remember**

A route that is not included in the application is not part of the running API.

### 3. Dependency Injection

**Concept**

FastAPI dependencies provide shared request logic such as authentication and database sessions.

**ALETHEIA implementation**

`Depends(require_api_key)` protects routes. `get_db()` supplies an async database session.

**Why**

Dependencies prevent repeated setup logic and create consistent request behavior.

**Failure**

A dependency can be present but too weak. A single shared API key authenticates a caller but does not identify or authorize a user.

**Remember**

Authentication answers “who has access?” Authorization answers “what may this caller do?”

### 4. Request Lifecycle: Webhook Ingestion

A real ALETHEIA request travels approximately as follows:

```text
HTTP request
→ FastAPI router
→ API-key dependency
→ client-IP extraction
→ Redis rate limit
→ raw request body
→ HMAC verification
→ optional Redis idempotency key
→ alert normalization
→ RemediationJob insert
→ database commit
→ ARQ enqueue
→ HTTP 202
```

Relevant function:

- `app/api/v1/endpoints/webhooks.py`: `ingest_alert`

Important transaction problem:

```text
database commit succeeds
→ queue enqueue fails
→ response is an error
→ job remains PENDING
→ no worker processes it
```

There is no transactional outbox connecting the database and queue.

### 5. Health and Readiness

**Concept**

Health endpoints communicate whether a service is alive and usable.

**ALETHEIA implementation**

- `/health`: liveness-style endpoint.
- `/ready`: checks database readiness.

**Not implemented**

Full readiness for:

- Redis
- ARQ worker availability
- Gemini
- Git repository availability
- GitHub connectivity

**Failure**

The service can report healthy while webhook ingestion or background processing is unusable.

---

## C. API Design

### REST and Resources

ALETHEIA exposes resources such as:

```text
/jobs
/jobs/{id}
/jobs/{id}/approve
/jobs/{id}/reject
/activity
```

The main resource is a remediation job.

### HTTP Methods and Status Codes

Examples:

- `POST /webhooks/ingest`: creates asynchronous work; returns `202`.
- `GET /jobs`: lists jobs.
- `GET /jobs/{id}`: retrieves a job.
- `POST /jobs/{id}/approve`: triggers approval.
- `POST /jobs/{id}/reject`: records rejection.

`202 Accepted` is appropriate for a request that has been accepted but not completed.

### Idempotency

**Concept**

An idempotent operation can be safely repeated without duplicating its effect.

**ALETHEIA**

Webhook idempotency uses an optional Redis key:

```text
SET key NX EX
```

This only works if the caller supplies a stable key.

**Weaknesses**

- No key means duplicate alerts can create duplicate jobs.
- The key can be consumed before database or queue success.
- PR creation has no equivalent idempotency check.
- Approval has no atomic compare-and-set.

### Authentication and Authorization

**Authentication**

`X-API-Key` is compared using `secrets.compare_digest`.

**Authorization**

Not implemented at a user or repository level.

Anyone with the shared key can:

- List jobs.
- View diffs.
- Approve jobs.
- Reject jobs.
- Supply arbitrary actor values.

### Rate Limiting

Redis sorted sets track timestamps in a sliding window.

Potential issue: timestamp strings are used as sorted-set members, so identical timestamps may overwrite one another.

---

## D. PostgreSQL and SQLAlchemy

### 1. Relational Database Fundamentals

**Concept**

A relational database stores structured records in tables with relationships and constraints.

**ALETHEIA tables**

#### `remediation_jobs`

Represents the lifecycle of an alert remediation attempt.

Likely fields include:

- Job ID
- Alert text
- Target file
- Status
- Generated patch
- Explanation
- Bug description
- Confidence
- Error message
- Timestamps

#### `audit_logs`

Represents events such as:

- Pipeline started
- Patch generated
- Dry run passed
- Approval granted
- PR created
- Pipeline failed

**Important limitation**

`AuditLog.job_id` is indexed but has no declared foreign key.

### 2. Primary Keys and Foreign Keys

A primary key uniquely identifies a row.

A foreign key enforces a relationship between tables.

ALETHEIA has job identifiers, but the audit-to-job relationship is not enforced by a foreign key.

**Why it matters**

An audit row can reference a job that does not exist, or a job can be deleted without its audit history being handled consistently.

### 3. SQLAlchemy ORM

**Concept**

An ORM maps Python classes to database tables.

**ALETHEIA**

- `RemediationJob` maps to the remediation jobs table.
- `AuditLog` maps to the audit logs table.

SQLAlchemy manages:

- Sessions
- Queries
- Transactions
- Connection pooling
- Object persistence

### 4. Transactions

**Concept**

A transaction groups operations so they commit together or roll back together.

**ALETHEIA incident creation**

```text
session.add(job)
await session.commit()
await enqueue(job.id)
```

The database transaction ends before queue submission.

**Failure scenario**

```text
DB commit succeeds
Queue fails
```

The database says a job exists, but Redis has no task. This is a distributed transaction problem.

**Production-grade version**

Use an outbox:

```text
Transaction:
    insert remediation job
    insert outbox event
commit

Dispatcher:
    read unsent outbox event
    enqueue ARQ job
    mark outbox event sent
```

The outbox makes queue dispatch recoverable.

### 5. Connection Pool

`create_async_engine()` uses:

- `pool_size=10`
- `max_overflow=20`
- `pool_pre_ping=True`

**Meaning**

The application normally maintains up to ten pooled connections and can temporarily create twenty more.

**Failure**

At higher load, database connection exhaustion can cause request failures or increased latency.

### 6. Migrations

**Concept**

Migrations version database schema changes over time.

**ALETHEIA**

`Base.metadata.create_all()` creates missing tables but does not safely evolve existing production schemas.

**NOT IMPLEMENTED**

- Alembic
- Schema version tracking
- Rollback migrations
- Deployment migration step

---

## E. Redis

### What Redis Is

Redis is an in-memory key-value and data-structure server.

It can be used for:

- Caching
- Locks
- Rate limits
- Sessions
- Queues
- Idempotency records

Do not call every Redis use caching. ALETHEIA uses Redis primarily for rate limiting, idempotency, and ARQ queue infrastructure.

### ALETHEIA Redis Uses

#### Rate limiting

`check_rate_limit()` uses a sorted set:

```text
remove old timestamps
count current timestamps
add timestamp
set expiration
```

#### Idempotency

`check_idempotency_key()` uses `SET NX EX` to claim a key for a limited period.

#### ARQ queue

ARQ stores jobs and results in Redis.

### Failure Modes

- Redis unavailable: webhook requests cannot complete normally.
- Idempotency claim consumed but downstream operation fails.
- TLS configuration may not be preserved correctly for `rediss://`.
- ARQ pool is not explicitly closed.

### Debugging

Inspect:

- `app/services/redis_store.py`
- `app/services/queue_service.py`
- `app/main.py`
- Redis URL handling in `app/config.py`

Ask:

1. Which Redis key is written?
2. What is its TTL?
3. What happens if the next database operation fails?
4. Which process owns the connection?
5. Is TLS enabled?

---

## F. ARQ and Background Jobs

### Why Background Jobs Exist

Gemini calls, Git operations, and GitHub operations can take longer than a normal HTTP request should remain open.

A queue allows:

```text
HTTP request accepts work quickly
worker performs long-running work later
frontend polls job state
```

### ALETHEIA Flow

```text
API
→ Redis
→ ARQ worker
→ process_remediation_job()
→ orchestrator
→ Gemini
→ Git validation
→ database state update
```

Relevant files:

- `app/services/queue_service.py`
- `app/worker.py`
- `app/services/orchestrator.py`

### Job Configuration

`WorkerSettings` includes:

- `max_jobs`
- `max_tries=3`
- `job_timeout=600`
- `keep_result=86400`

There is also a process-local semaphore.

### Important Retry Reality

Although ARQ is configured for retries, the orchestrator catches failures and returns a failure dictionary.

Therefore:

```text
exception
→ caught by orchestrator
→ job marked FAILED
→ normal return
→ ARQ may not retry
```

Gemini itself has tenacity retry logic for selected transient errors.

### Worker Crash

If the process crashes before completion, ARQ may retry depending on job visibility and configuration.

But side effects may already have occurred:

- Branch may exist.
- Push may have succeeded.
- PR may exist.
- Database may still say `FAILED` or `WAIT_FOR_APPROVAL`.

This requires idempotent reconciliation, which is not implemented.

---

## G. Concurrency

### Race Conditions

A race condition occurs when the result depends on timing between concurrent operations.

### Two Approvals

Current flow:

```text
Request A reads status WAIT_FOR_APPROVAL
Request B reads status WAIT_FOR_APPROVAL

A dry-runs patch
B dry-runs patch

A records approval
B records approval

A creates branch/PR
B creates branch/PR
```

The implementation uses an atomic approval claim equivalent to:

```sql
UPDATE jobs
SET status = 'APPROVING'
WHERE id = :id
  AND status IN ('VALIDATION_PASSED', 'DRY_RUN_PASSED', 'WAIT_FOR_APPROVAL')
```

Only one request should win the transition. A later request returns the persisted PR identity when available or receives a conflict before side effects.

Only one request should win the transition. The second should receive a conflict response such as `409 Conflict`.

### Distributed Coordination

A Python semaphore only coordinates tasks inside one process. Multiple worker processes do not share it.

Production alternatives include:

- Database row locks.
- Compare-and-set updates.
- Redis distributed locks with care.
- Unique constraints on PR identity.
- Idempotency keys for external operations.

### Optimistic Concurrency

Store a version number or compare the current state before updating.

Example:

```text
Expected version: 4
Update only if version = 4
New version: 5
```

If another worker already changed it, the update affects zero rows.

---

## H. Git Engineering

### Core Concepts

- Repository: Git-managed history and metadata.
- Working tree: checked-out files.
- Branch: movable pointer to commits.
- Commit: immutable snapshot reference.
- Diff: difference between file states.
- Patch: instructions for applying a diff.
- Worktree: another working directory attached to the same repository.
- `git apply --check`: tests whether a patch can apply.

### ALETHEIA Patch Path

#### Dry run

`apply_unified_diff()` calls Git in the configured repository directory.

Important correction:

> The dry run does not use a temporary worktree.

#### PR creation

`github_service.py` creates a temporary detached worktree, creates a branch, applies the patch, commits, and pushes.

### Why Worktrees Matter

Without worktrees, concurrent jobs could modify the same working tree.

A worktree allows separate filesystem directories for separate branch operations.

### What `git apply --check` Proves

It indicates that:

- Git recognizes the patch.
- The context likely matches.
- The patch can likely be applied under the chosen flags.

### What It Does Not Prove

It does not prove:

- The bug is fixed.
- Tests pass.
- The code is secure.
- The patch is minimal.
- Only the intended file changes.
- The patch is safe to merge.
- The repository will not change afterward.

### Git Risks

- The main checkout is used during dry run.
- Three-way application may make patch interpretation more permissive.
- The PR flow stages all changes with `git add -A`.
- Remote branches are not reconciled after partial failure.
- No branch collision policy exists.

---

## I. GitHub API

### What GitHub Provides

GitHub stores repositories, branches, commits, pull requests, checks, and reviews.

### ALETHEIA PR Flow

`create_pull_request()`:

```text
validate repository
→ create temporary worktree
→ create branch
→ apply patch
→ git add -A
→ git commit
→ git push
→ HTTP POST to GitHub pull-request API
→ remove worktree
```

### Authentication

Two forms are used:

- Git push URL contains the token.
- GitHub API uses an authorization header.

**Security issue**

The token-bearing push URL is passed to a subprocess. It may be visible through process inspection or diagnostics.

### Failure Cases

#### GitHub unavailable

The branch may already be pushed, but PR creation fails. The database may say `FAILED`, and retry may create duplicate work.

#### PR created but DB update fails

The real PR exists but the system does not know it. A retry may create another branch or PR.

#### Invalid token

Push or API calls fail. Error sanitization attempts to redact token material.

#### Missing token

The service returns `DEMO MODE - NO REAL PR CREATED` with no fabricated URL or PR number. This behavior is allowed only for an explicit non-production demonstration.

#### Rate limits

No complete GitHub rate-limit management or retry/reconciliation system is implemented.

---

## J. Docker

### Concepts

- Image: packaged filesystem and runtime.
- Container: running instance of an image.
- Dockerfile: image build instructions.
- Compose: multi-container local orchestration.
- Volume: persisted or shared filesystem.
- Network: container-to-container communication layer.

### ALETHEIA Containers

```text
Frontend
   ↓ HTTP
Backend API
   ├── PostgreSQL
   ├── Redis
   └── ARQ worker
          ├── Gemini
          ├── Git
          └── GitHub
```

Files:

- `docker-compose.yml`
- `Dockerfile.backend`
- `Dockerfile.worker`
- `frontend/Dockerfile.frontend`
- `render.yaml`

### Important Deployment Reality

The repository is copied into the backend and worker images. With `REPO_PATH=.` the worker may operate on its own container checkout.

This is not the same as operating on a mounted, current, externally managed repository.

**NOT VERIFIED**

- Render deployment
- Neon database
- Upstash Redis
- Vercel frontend
- Live GitHub/Gemini integration

---

## K. Security

### Authentication

Threat: unauthorized callers invoke job and approval endpoints.

Defense: API key with `secrets.compare_digest`.

Weakness: development mode can bypass authentication, and there is only one shared identity.

### Authorization

Threat: an authenticated caller views or approves another user’s job.

Defense: none beyond possession of the shared key.

**NOT IMPLEMENTED**

- Users
- Roles
- Repository scopes
- Tenant isolation
- Per-job ownership

### HMAC Webhook Verification

Threat: attackers forge monitoring alerts.

Defense: HMAC-SHA256 over the raw request body.

Weakness: if `WEBHOOK_SECRET` is empty, verification accepts the request.

### Replay Attacks

Threat: a valid old webhook is resent repeatedly.

Defense: optional idempotency key.

Weakness:

- Caller must provide the key.
- No timestamp/nonce verification is tied to the signature.
- No server-derived alert fingerprint exists.

### Path Traversal

Threat: target file escapes the repository or reads sensitive files.

Defense:

- Resolve paths.
- Reject absolute paths and `..`.
- Block `.env`, keys, certificates, and `.git`.

Weakness: generated diff path validation is partial and requires stronger allowlisting.

### Subprocess Security

Threat: shell injection or token exposure.

Positive control:

- Git commands use argument arrays rather than shell strings.

Weakness:

- Git push URL contains a token.
- Repository Git configuration and hooks require isolation.
- Generated code is not executed by the app, but Git operations still interact with potentially malicious repositories.

### Prompt Injection

Threat: malicious logs or source comments instruct the model to produce unsafe changes.

Defense: XML-style delimiters.

Weakness: delimiters do not make content trusted or instruction-free.

### Least Privilege

Containers use a non-root user, which is positive.

Not implemented:

- Fine-grained GitHub token permissions.
- Per-repository credentials.
- Separate sandbox identity for generated patch operations.
- Runtime resource limits.

---

## L. Observability

### Logs

Standard Python logging exists.

Weaknesses:

- Ordinary text logs.
- No correlation IDs.
- No complete structured redaction policy.
- No durable event stream.

### Audit Logs

`AuditLog` records business events.

This is not the same as operational observability.

`_record_audit()` swallows its own failures, so audit loss does not stop the pipeline.

### Metrics

**NOT IMPLEMENTED**

- Queue depth
- Queue age
- Gemini latency
- Token usage
- Model cost
- GitHub latency
- Patch acceptance
- Test pass rate
- Alert-to-PR time
- Error rate
- Worker utilization
- MTTR

### Health

`/health` is liveness-like.

`/ready` checks PostgreSQL.

A production readiness endpoint should also account for Redis and worker availability.

---

## M. Testing

### Unit Tests

Test isolated functions such as:

- Alert normalization
- Signature verification
- Path validation
- Token scrubbing

These provide confidence in local logic only.

### Integration Tests

Should test real boundaries such as:

- PostgreSQL
- Redis
- ARQ
- Git subprocess
- GitHub API mock server

ALETHEIA has little of this.

### End-to-End Tests

Should run:

```text
webhook
→ database
→ queue
→ worker
→ patch
→ Git validation
→ approval
→ PR mock
```

**NOT IMPLEMENTED**

### Existing Test Coverage

The repository has 16 test functions covering:

- Health
- Alert normalization
- HMAC
- HTTP 202 ingestion
- Direct patch denial
- Traversal and sensitive-file rejection
- Credential scrubbing
- Mocked orchestrator success/failure paths

They do not prove live service behavior.

---

## Production-Grade Mental Model

```text
Concept → current implementation → tradeoff → failure → production version

Database + queue → separate commits → simple → stuck PENDING job → outbox
Patch check → textual applicability → fast → wrong code accepted → isolated tests/policy gates
Shared API key → simple authentication → low setup → no identity → users/RBAC/scopes
ARQ retries → at-least-once work → recovery → duplicate side effects → idempotent operations/reconciliation
Human approval → safety boundary → slower → race/weak audit → atomic transitions and verified identity
```

## Backend Interview Questions

1. Why return HTTP 202 for webhook ingestion?
2. Why is a database commit followed by queue enqueue unsafe?
3. What does async improve?
4. Why does ARQ not guarantee exactly-once execution?
5. What does Pydantic validate?
6. Why is `create_all` not a migration system?
7. What does `git apply --check` prove?
8. Why is a worktree useful?
9. Why is a shared API key not authorization?
10. How would you prevent two approvals from creating duplicate PRs?
11. Why is prompt injection possible through logs?
12. What metrics would prove this product works?

## What To Remember

ALETHEIA is an asynchronous stateful workflow. Its hardest engineering problems are not syntax or framework usage. They are the boundaries between systems: PostgreSQL versus Redis, worker retries versus side effects, model output versus Git, approval versus authorization, and GitHub reality versus database state.
