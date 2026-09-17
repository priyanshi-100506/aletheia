# ALETHEIA Handover & Architecture Document

## 1. Project Summary

ALETHEIA is a constrained incident-to-validated-patch portfolio workflow with a FastAPI backend, an asynchronous ARQ + Redis worker pipeline, and a React/Vite operational command center frontend. It ingests monitoring alerts (Datadog, Prometheus, generic webhooks), normalizes payloads, generates unified code diff patches using Google Gemini 2.0 Flash when configured, validates patches in isolated temporary checkouts with targeted tests, and exposes a human-in-the-loop approval workflow for GitHub Pull Requests.

**Scope boundary:** ALETHEIA is not currently a fully autonomous production remediation system. The deterministic portfolio runner uses fixture-backed patches and zero Gemini calls. Without GitHub credentials, it reports `DEMO MODE - NO REAL PR CREATED`.

The frontend is an operational command center built under the Orchid Noir design system (`frontend_blueprint.md`).

### Current Robustness Assessment

**Overall: 5/10.**

- **Local demo path: 7/10.** The tested path is reliable when PostgreSQL, Redis, one ARQ worker, and the Vite frontend are running. `DEMO_MODE=true` uses a deterministic transaction fixture and avoids Gemini credits. Backend tests, deterministic scenarios, and the frontend build pass.
- **Production path: 3/10.** Real Gemini and GitHub integrations remain optional and are not covered by end-to-end integration tests. Schema upgrades are currently compatibility SQL in startup rather than versioned migrations. Worker health, retry recovery, and semantic patch correctness are not yet proven.

The system is suitable for a controlled portfolio/demo video, but it should not be described as production-robust autonomous remediation.

---

## 2. Production & Security Upgrades Delivered

The platform has been hardened from a prototype into a credible, reproducible portfolio demonstration:

### Asynchronous Queue & Distributed State
- **ARQ + Redis Queue (`app/worker.py`, `app/services/queue_service.py`):** Asynchronous background job processing with deterministic job IDs, configurable concurrency, and automatic retries.
- **Sliding-Window Rate Limiting (`app/services/redis_store.py`):** Redis sorted-set rate limiter protecting webhook ingestion endpoints against DoS across multi-node deployments.
- **Distributed Idempotency:** Redis `SET NX EX` deduplication preventing duplicate execution on webhook retries.

### Security & Ingestion Safeguards
- **HMAC SHA-256 Webhook Verification (`X-Hub-Signature-256`):** Prevents webhook spoofing by validating incoming payload signatures against `WEBHOOK_SECRET`.
- **Path Traversal & Sensitive File Defense (`_safe_read_target_file`):** Strictly enforces `Path.is_relative_to(repo_root)` and blocks access to `.env`, `id_rsa`, `*.pem`, `*.key` from LLM context.
- **Prompt Injection Defense:** Encapsulates raw error logs and source files in strict XML tags (`<error_log>`, `<target_file>`).
- **Direct Apply Lockdown:** `POST /api/v1/patch/apply` returns `403 Forbidden` for `dry_run=False`, ensuring all live mutations require the approval-gated PR workflow.
- **Explicit Security Modes:** Protected mode requires `API_KEY` and `WEBHOOK_SECRET`. Unsigned local requests are allowed only with explicit non-production `DEMO_MODE=true`.
- **Target-File Policy:** Unified diffs reject absolute paths, traversal, missing headers, and modifications outside the requested target file.
- **Isolated Test Validation:** Patches are applied in a temporary checkout and validated with targeted tests or syntax checks. `PATCH_APPLIED`, `VALIDATION_PASSED`, and `VALIDATION_FAILED` are distinct states.
- **Honest GitHub Behavior:** Demo mode has no fabricated PR URL or number. Configured GitHub mode searches for an existing branch PR before creating another one.
- **Credential & Token Scrubbing (`_sanitize_output`):** Redacts PATs, GitHub tokens, and auth remote URLs from git errors, audit logs, and HTTP error responses.
- **TOCTOU Race Prevention:** Performs pre-approval verification against repository `HEAD` before opening PR branches.

### Reliability & Audit Logging
- **Append-Only Audit Log (`audit_logs` table):** Tracks lifecycle events including `PATCH_GENERATED`, `PATCH_APPLIED`, `VALIDATION_PASSED`, `VALIDATION_FAILED`, `APPROVAL_GRANTED`, `REJECTED`, and `PR_CREATED`.
- **Exponential Backoff Retries:** Handles transient Gemini LLM or GitHub API rate-limits gracefully with `tenacity`.
- **Structured LLM Generation:** Pydantic `PatchResult` schema enforced via Gemini `response_schema`.
- **Demo-credit control:** With `DEMO_MODE=true`, `transaction_service.py` uses a deterministic fixture patch and does not call Gemini. Other target files require `DEMO_MODE=false` and a configured Gemini key unless new fixtures are added.

### Frontend Command Center (Orchid Noir System)
- **5 Operational Screens:**
  1. **Incidents:** Dense table displaying open incidents, confidence, age, and status.
  2. **Review Queue:** Safety-critical view filtered specifically for validated patches awaiting human approval.
  3. **Repositories:** Displays Git connection health, worktree isolation status, and diff policy limits.
  4. **Activity:** Real-time audit log stream.
  5. **Settings:** Integration status, HMAC secrets, and concurrency limits.
- **Diff Viewer Component (`DiffViewer.tsx`):** Split/unified code diff viewer with line numbers, copy actions, patch size risk warnings, and approval/rejection modals.
- **Alert Ingestion Modal (`AlertIngestModal.tsx`):** UI component to simulate and ingest alert trace payloads directly from the browser.

### Optional Free-Tier Demonstration Deployment
- **Render:** Free Web Service running FastAPI + ARQ worker in-process (`RUN_WORKER_INPROCESS=true`).
- **Neon:** Free Serverless PostgreSQL with auto-handled SSL (`sslmode=require`).
- **Upstash:** Free Serverless TLS Redis (`rediss://...`).
- **Vercel:** Free Vite React hosting with SPA routing rewrites (`frontend/vercel.json`).

---

## 3. Current Runtime Commands

| Component | Address | Start command |
| --- | --- | --- |
| FastAPI backend | `http://127.0.0.1:8001` | `uv run uvicorn app.main:app --host 127.0.0.1 --port 8001` |
| ARQ worker | — | `uv run arq app.worker.WorkerSettings` |
| React frontend | `http://localhost:5173` | `cd frontend; npm run dev -- --host localhost --port 5173` |
| PostgreSQL & Redis (local) | `127.0.0.1:5435`, `127.0.0.1:6379` | `docker compose up -d postgres redis` |
| Full Stack Docker | `http://127.0.0.1:5174` | `docker compose up --build` |

---

## 4. Environment Configuration (`.env`)

```env
DATABASE_URL=postgresql+asyncpg://aletheia_user:aletheia_password@127.0.0.1:5435/aletheia_db
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-3.6-flash
GITHUB_TOKEN=your_github_personal_access_token
GITHUB_REPOSITORY=priyanshi-100506/aletheia
GITHUB_BASE_BRANCH=main
REDIS_URL=redis://127.0.0.1:6379/0
API_KEY=your_32_char_secret_key
WEBHOOK_SECRET=your_hmac_secret
DEMO_MODE=true
RUN_WORKER_INPROCESS=false
ENVIRONMENT=development
FRONTEND_ORIGINS=http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:5174,http://localhost:5174
```

Do not commit real credentials. Rotate any credential that has been pasted into chat, logs, screenshots, or shared files.

---

## 5. Automated Test & Verification Commands

Backend test suite (**20/20 tests passing at last validation**):
```powershell
uv run pytest tests/ -v
uv run python -m compileall -q app
uv run python scripts/run_portfolio_validation.py --all
```

Frontend checks:
```powershell
cd frontend
npm run build
```

Latest verified local checks:

- `uv run pytest tests/ -q` -> `20 passed`
- `uv run python scripts/run_scenario.py --all` -> all expected PASS/SAFE FAILURE results
- Frontend TypeScript check and Vite production build -> passed
- Deterministic demo fixture -> `transaction_service.py`, confidence `0.98`

The portfolio runner creates five temporary Git repositories, verifies that each baseline test fails, applies a deterministic constrained patch in an isolated checkout, runs the relevant pytest command, records a local approval, and calls the GitHub service. It uses zero Gemini calls. Without `GITHUB_TOKEN`, it reports `DEMO MODE - NO REAL PR CREATED`.

## 7. Known Issues And Hardening Priorities

Prioritize these in order before claiming production readiness:

1. Add Alembic or another versioned migration system. Startup currently repairs legacy enum values and PR columns with compatibility SQL.
2. Add a real Postgres/Redis/ARQ integration test covering ingest -> worker -> validation -> approval/rejection.
3. Add worker health/readiness reporting and ensure deployment runs exactly one intended worker per queue.
4. Persist validation commands and test results; the main orchestrator currently falls back to `py_compile` for Python targets unless a command is explicitly supplied.
5. Add mocked Gemini and GitHub HTTP integration tests, including model-not-found, rate-limit, existing-PR, and GitHub 4xx/5xx cases.
6. Make webhook idempotency transactional with job creation/enqueue recovery; currently a key can be reserved before a later enqueue failure.
7. Add frontend tests for ingest, polling, offline API errors, approval gating, rejection, and simulated PR display.
8. Replace browser-visible API-key use with an authenticated session/proxy for any real deployment.
9. Rotate exposed credentials and keep `.env` untracked; use a secret manager outside local development.

### Demo Startup

```powershell
docker compose up postgres redis -d
uv run uvicorn app.main:app --port 8001 --reload
uv run arq app.worker.WorkerSettings
cd frontend; npm run dev -- --host localhost --port 5173
```

Open `http://localhost:5173/`. For the zero-credit demo, ingest an alert targeting `transaction_service.py`. Wait for `VALIDATION_PASSED` or `WAIT_FOR_APPROVAL` before approving. A simulated approval reports `DEMO MODE - NO REAL PR CREATED`.

## 8. Deployment Readiness Runbook

### Preflight: Do Not Deploy Until All Pass

Run these checks from the repository root:

```powershell
docker compose up postgres redis -d
uv run pytest tests/ -q
uv run python scripts/run_scenario.py --all
Push-Location frontend; npm run build; Pop-Location
```

Then verify:

```text
GET  http://127.0.0.1:8001/health -> 200
GET  http://127.0.0.1:8001/ready  -> 200
GET  http://127.0.0.1:8001/api/v1/jobs -> 200 with authentication configured
```

Run exactly one API process and exactly one ARQ worker per Redis queue during a local demo. Duplicate reloaders or workers can produce port conflicts, duplicate processing, and confusing job states.

### Protected Deployment Configuration

For any non-demo deployment, use:

```env
ENVIRONMENT=production
DEMO_MODE=false
API_KEY=<strong-secret>
WEBHOOK_SECRET=<strong-secret>
GEMINI_API_KEY=<provider-secret>
GEMINI_MODEL=<verified-available-model>
GITHUB_TOKEN=<least-privilege-token>
GITHUB_REPOSITORY=<owner>/<repo>
DATABASE_URL=<managed-postgres-url>
REDIS_URL=<managed-redis-url>
FRONTEND_ORIGINS=<exact-frontend-origin>
```

Never deploy with blank `API_KEY`, blank `WEBHOOK_SECRET`, demo mode enabled, or credentials copied into source control. Rotate credentials that appeared in chat, logs, screenshots, or shared files.

### Failure Recovery Matrix

| Symptom | Likely cause | Recovery |
| --- | --- | --- |
| Frontend `Failed to fetch` | API stopped, wrong port, or CORS origin mismatch | Check `/health`, confirm API base URL, confirm `FRONTEND_ORIGINS`, restart one API process |
| Jobs endpoint returns `500` | PostgreSQL unavailable or stale schema | Start Postgres, check `/ready`, restart API so compatibility checks run, inspect API logs |
| Job remains `PENDING` | Worker is stopped or Redis is unavailable | Check Redis, stop duplicate workers, start one `uv run arq app.worker.WorkerSettings` |
| Job remains `GENERATING` | Model call is slow, unavailable, or worker has stopped | Inspect worker logs; do not approve; retry with demo fixture or repair provider configuration |
| Job remains `GENERATED` | Validation failed or an old worker crashed while saving status | Inspect worker logs and database status; restart the corrected worker; resubmit rather than approving |
| Job is `VALIDATION_FAILED` | Patch does not apply or validation command failed | Review `error_message`, fix the fixture/model output, and submit a new job |
| Approval returns `400` | Job is not validation-ready | Approve only `VALIDATION_PASSED`, `DRY_RUN_PASSED`, or `WAIT_FOR_APPROVAL` |
| Approval returns `500` | GitHub/demo PR creation failed | Check token, repository, branch, remote, and GitHub API response; do not retry blindly if a branch may already exist |
| Duplicate jobs appear | Duplicate webhook or worker/process race | Use `X-Idempotency-Key`, stop duplicate workers, inspect ARQ job IDs and audit events |

### Safe State Rules

1. Never approve a job with status `PENDING`, `GENERATING`, `GENERATED`, `PATCH_APPLIED`, `VALIDATION_FAILED`, or `FAILED`.
2. Never treat a visible diff as proof that validation passed.
3. Never delete the PostgreSQL volume to fix an application error; preserve evidence and repair the schema with a versioned migration before production deployment.
4. Never enable real GitHub credentials just for a demo video.
5. If a job state is ambiguous, reject or resubmit it after collecting the job record, worker log, and audit events.

### Production Blockers

The following must be completed before calling the system production-robust:

- Replace startup schema repair SQL with versioned Alembic migrations and test upgrades from an old database.
- Add an integration test for webhook -> Redis -> ARQ -> PostgreSQL -> approval/rejection.
- Add worker readiness, queue depth, retry, timeout, and dead-letter monitoring.
- Persist validation commands and actual test evidence instead of relying on Python syntax compilation by default.
- Add mocked Gemini and GitHub integration tests for timeout, 4xx, 5xx, malformed output, and existing-PR responses.
- Make idempotency reservation recoverable when database insertion or queue enqueue fails.
- Add deployment rollback and database backup/restore procedures.
- Remove browser-visible API keys from production authentication.

Until those controls exist, deploy only as a controlled demonstration or internal pilot with explicit human review.

---

## 6. Controlled Demo-Ready Test & Ingestion Architecture

### Target Repository Integration
- **Allowlisted Target:** `priyanshi-100506/aletheia-demo-bugs` (governed by `settings.ALLOWED_REPOS`).
- **Deterministic Scenarios (`app/constants.py`):**
  - `scenario_1`: `tests/test_users.py::test_display_name_none` -> `incident_demo/services/users.py`
  - `scenario_2`: `tests/test_external_api.py::test_external_api_error` -> `incident_demo/services/external_api.py`
  - `scenario_3`: `tests/test_validation.py::test_api_validation` -> `incident_demo/schemas.py`
  - `scenario_4`: `tests/test_reports.py::test_db_query_logic` -> `incident_demo/services/reports.py`
  - `scenario_5`: `tests/test_regression.py::test_regression` -> `incident_demo/services/utils.py`

### Isolated Validation Pipeline (`app/services/patch_validation.py`)
1. Clones/copies the target repository to an ephemeral temporary directory (`tempfile.TemporaryDirectory`).
2. Runs the target test to establish and persist baseline failure (`baseline_target_result`).
3. Runs the full test suite to capture baseline regression status (`baseline_full_result`).
4. Applies the unified patch using `git apply --recount -3`.
5. Re-runs the target test; asserts it passes (`postfix_target_result`).
6. Re-runs the full test suite to confirm unrelated intentional failures remain unchanged without introducing regressions (`postfix_full_result`).
7. Stores full JSON evidence into `evidence_json` on the `RemediationJob`.

### Verification Script
Run the automated sanity check:
```powershell
.\scripts\verify_demo.ps1
```

---

## 7. Engineering Documentation & Learning Guide

- [documentation.md](documentation.md) — Comprehensive technical reference and decision log.
- [DEPLOY.md](DEPLOY.md) — Free-tier deployment guide with protected/demo-mode caveats.
- [learnings.md](learnings.md) — First-principles engineering concepts, security deep dives, and interview talking points.
- [CHANGELOG.md](CHANGELOG.md) — Release notes and known limitations.
