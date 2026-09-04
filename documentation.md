# ALETHEIA Technical Architecture & System Blueprint

## System Topology

ALETHEIA follows this production execution topology:

```text
Monitoring Sources (Datadog / Prometheus / Custom Webhooks)
        │ HTTP POST /api/v1/webhooks/ingest (HMAC SHA-256 Signature Verification)
        ▼
FastAPI Ingestion & Security Gate (Rate Limiting + Idempotency Check)
        │ HTTP 202 Accepted { status: "processing", job_id: "uuid" }
        ▼
FastAPI Background Remediation Worker (Tenacity Exponential Backoff Retries)
        │ Read Source Code & Prompt -> Gemini 3.6 / 1.5 Flash Structured JSON
        ▼
Gemini Patch Generation -> Unified Git Diff (.patch)
        │ Apply Diff in Isolated Temporary Worktree (git worktree)
        ▼
Local Dry-Run Validation (status: DRY_RUN_PASSED)
        │ Halts Pipeline & Records Audit Event (audit_logs table)
        ▼
Human Safety Approval Gate (React Operational UI / POST /api/v1/jobs/{id}/approve)
        │ Explicit Human Approval Granted
        ▼
Git Worktree Commit, Branch Push & GitHub REST API Pull Request Creation
```

Supported alert sources are generic HTTP payloads, Datadog-style alerts, and Prometheus-style firing alert groups. PostgreSQL stores remediation job records, unified code diffs, execution state, failure logs, and append-only security audit events.

---

## Module Tree

```text
app/
    api/v1/endpoints/approval.py    Server-side approval, rejection, and activity audit endpoints
    api/v1/endpoints/jobs.py        Authenticated job listing and status lookup endpoints
    api/v1/endpoints/patch.py       Patch generation and direct dry-run application endpoints
    api/v1/endpoints/webhooks.py    HMAC-verified, rate-limited alert ingestion endpoint
    api/v1/router.py                v1 route aggregator
    config.py                       Environment and security settings configuration
    core/security.py                Signature verification, rate limiting, and idempotency logic
    db/database.py                  Async SQLAlchemy engine, AsyncSessionLocal, and init_db
    models/audit.py                 AuditLog ORM model for security trail
    models/remediation.py           RemediationJob ORM model and PatchStatus enum
    schemas/api.py                  Standard API request and response schemas
    schemas/patch.py                Pydantic PatchResult schema for LLM structured output
    schemas/webhook.py              Vendor payload normalization rules
    services/git_applier.py         Local unified diff validation and dry-run application
    services/github_service.py      Git branch push and GitHub API PR creation
    services/orchestrator.py        End-to-end background remediation worker with retries
    services/patcher.py             Gemini patch generation with source code context
    services/security_service.py    HMAC signature, rate limiter, and idempotency checkers
    main.py                         FastAPI application, CORS, health, readiness, and lifespan
```

---

## Data Flow & Pipeline Workflow

1. **Ingest & Verify:** The webhook endpoint receives an alert payload, verifies the HMAC SHA-256 signature (`X-Hub-Signature-256`), checks rate limits, and validates `X-Idempotency-Key`.
2. **Normalize:** `normalize_alert` maps provider-specific telemetry into canonical `(error_log, target_file)`.
3. **Queue:** A job ID is generated and returned immediately with HTTP `202`.
4. **Analyze & Fix:** The background worker sets status to `GENERATING`, reads the target file from disk, and invokes Gemini AI to produce structured JSON (`PatchResult`).
5. **Dry-Run Test:** The patcher executes `git apply --check` inside an isolated temporary Git worktree (`git worktree`). Upon passing, status moves to `DRY_RUN_PASSED` and an `AWAITING_APPROVAL` audit event is logged.
6. **Human Approval Gate:** An on-call engineer inspects the code diff in the React UI and clicks **Approve & Push PR**.
7. **PR Creation:** The server verifies authorization via `POST /api/v1/jobs/{job_id}/approve`, creates branch `fix/aletheia-{job_id}`, commits the patch, pushes to GitHub `origin`, and creates a GitHub Pull Request via REST API.

---

## Configuration Reference

| Variable | Purpose | Default |
| --- | --- | --- |
| `DATABASE_URL` | Async PostgreSQL connection string | `postgresql+asyncpg://aletheia_user:aletheia_password@127.0.0.1:5435/aletheia_db` |
| `GEMINI_API_KEY` | Google Gemini API Authentication Key | Unset |
| `GITHUB_TOKEN` | GitHub Personal Access Token (PAT) for PR creation | Unset (Falls back to simulation mode) |
| `GITHUB_REPOSITORY` | Target GitHub repository (`owner/repo`) | `priyanshi-100506/aletheia` |
| `GITHUB_BASE_BRANCH` | Base target branch for pull requests | `main` |
| `WEBHOOK_SECRET` | HMAC SHA-256 signing secret for webhooks | Unset |
| `REPO_PATH` | Local Git repository checkout path | `.` |

---

## Security & Protection Architecture

1. **HMAC Signature Verification:** Prevents unauthorized HTTP webhook requests.
2. **Rate Limiting & Anti-Spam:** Sliding-window rate limiter prevents DoS attacks on alert ingestion routes.
3. **Idempotency Keys:** Suppresses duplicate execution of identical alert trace payloads.
4. **Git Worktree Isolation:** Prevents concurrent remediation tasks from altering the primary working directory or causing race conditions.
5. **Server-Side Approval Enforcement:** Prevents automated unreviewed AI code pushes to remote repositories.
6. **Append-Only Audit Trail:** Stores structured security events in the `audit_logs` SQL table.

---

## Frontend Command Center Architecture (Orchid Noir)

The React frontend lives in `frontend/` and starts via `npx vite --host 127.0.0.1 --port 5174`. It implements 5 operational screens:

1. **Incident Command Center:** Live incident table with filter bar and quick detail drawer.
2. **Review Queue:** Safety-critical view dedicated to dry-run validated patches.
3. **Diff Viewer (`DiffViewer.tsx`):** Split/unified code diff viewer with line numbers, copy buttons, patch size risk banners, and approval/rejection modals.
4. **Repositories View:** Displays active repository connections, worktree isolation status, and diff limits.
5. **Activity Log:** Real-time audit stream fetched from `GET /api/v1/activity`.
6. **Settings & Ingest Modal:** Configuration panels and browser alert trigger dialog.

---

## Multi-Container Docker Deployment

The system is fully containerized using Docker & Docker Compose:

```bash
docker compose up --build
```

- **PostgreSQL 16 + pgvector:** Database service exposed on port `5435`.
- **FastAPI Backend (`Dockerfile.backend`):** Python 3.13 backend service on port `8001`.
- **React Frontend (`Dockerfile.frontend`):** Nginx-served single-page app on port `5174`.
