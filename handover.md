# ALETHEIA Handover & Architecture Document

## 1. Project Summary

ALETHEIA is an autonomous AIOps incident remediation platform with a FastAPI backend, an asynchronous ARQ + Redis worker pipeline, and a React/Vite operational command center frontend. It ingests monitoring alerts (Datadog, Prometheus, generic webhooks), normalizes payloads, generates unified code diff patches using Google Gemini 2.0 Flash AI, validates patches inside isolated Git worktrees, and exposes a human-in-the-loop approval workflow to open GitHub Pull Requests.

The frontend is an operational command center built under the Orchid Noir design system (`frontend_blueprint.md`).

---

## 2. Production & Security Upgrades Delivered

The platform has been hardened from a prototype into an engineering-grade, production-ready AIOps platform:

### Asynchronous Queue & Distributed State
- **ARQ + Redis Queue (`app/worker.py`, `app/services/queue_service.py`):** Asynchronous background job processing with deterministic job IDs, configurable concurrency, and automatic retries.
- **Sliding-Window Rate Limiting (`app/services/redis_store.py`):** Redis sorted-set rate limiter protecting webhook ingestion endpoints against DoS across multi-node deployments.
- **Distributed Idempotency:** Redis `SET NX EX` deduplication preventing duplicate execution on webhook retries.

### Security & Ingestion Safeguards
- **HMAC SHA-256 Webhook Verification (`X-Hub-Signature-256`):** Prevents webhook spoofing by validating incoming payload signatures against `WEBHOOK_SECRET`.
- **Path Traversal & Sensitive File Defense (`_safe_read_target_file`):** Strictly enforces `Path.is_relative_to(repo_root)` and blocks access to `.env`, `id_rsa`, `*.pem`, `*.key` from LLM context.
- **Prompt Injection Defense:** Encapsulates raw error logs and source files in strict XML tags (`<error_log>`, `<target_file>`).
- **Direct Apply Lockdown:** `POST /api/v1/patch/apply` returns `403 Forbidden` for `dry_run=False`, ensuring all live mutations require the approval-gated PR workflow.
- **Credential & Token Scrubbing (`_sanitize_output`):** Redacts PATs, GitHub tokens, and auth remote URLs from git errors, audit logs, and HTTP error responses.
- **TOCTOU Race Prevention:** Performs pre-approval dry-run verification against repository `HEAD` before opening PR branches.

### Reliability & Audit Logging
- **Append-Only Audit Log (`audit_logs` table):** Tracks all pipeline lifecycle events (`WEBHOOK_INGEST`, `PATCH_GENERATED`, `DRY_RUN_PASSED`, `APPROVAL_GRANTED`, `REJECTED`, `PR_CREATED`) for auditability.
- **Exponential Backoff Retries:** Handles transient Gemini LLM or GitHub API rate-limits gracefully with `tenacity`.
- **Structured LLM Generation:** Pydantic `PatchResult` schema enforced via Gemini `response_schema`.

### Frontend Command Center (Orchid Noir System)
- **5 Operational Screens:**
  1. **Incidents:** Dense table displaying open incidents, confidence, age, and status.
  2. **Review Queue:** Safety-critical view filtered specifically for dry-run validated patches.
  3. **Repositories:** Displays Git connection health, worktree isolation status, and diff policy limits.
  4. **Activity:** Real-time audit log stream.
  5. **Settings:** Integration status, HMAC secrets, and concurrency limits.
- **Diff Viewer Component (`DiffViewer.tsx`):** Split/unified code diff viewer with line numbers, copy actions, patch size risk warnings, and approval/rejection modals.
- **Alert Ingestion Modal (`AlertIngestModal.tsx`):** UI component to simulate and ingest alert trace payloads directly from the browser.

### Cloud Deployment (100% Free-Tier Architecture)
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
| React frontend | `http://127.0.0.1:5174` | `cd frontend && npm run dev` |
| PostgreSQL & Redis (local) | `127.0.0.1:5435`, `127.0.0.1:6379` | `docker compose up -d postgres redis` |
| Full Stack Docker | `http://127.0.0.1:5174` | `docker compose up --build` |

---

## 4. Environment Configuration (`.env`)

```env
DATABASE_URL=postgresql+asyncpg://aletheia_user:aletheia_password@127.0.0.1:5435/aletheia_db
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-2.0-flash
GITHUB_TOKEN=your_github_personal_access_token
GITHUB_REPOSITORY=priyanshi-100506/aletheia
GITHUB_BASE_BRANCH=main
REDIS_URL=redis://127.0.0.1:6379/0
API_KEY=your_32_char_secret_key
WEBHOOK_SECRET=your_hmac_secret
RUN_WORKER_INPROCESS=false
ENVIRONMENT=development
```

---

## 5. Automated Test & Verification Commands

Backend test suite (**16/16 tests passing**):
```powershell
uv run pytest tests/ -v
uv run python -m compileall -q app
```

Frontend checks:
```powershell
cd frontend
npm run build
```

---

## 6. Engineering Documentation & Learning Guide

- [documentation.md](file:///c:/Users/USER/Documents/aletheia/documentation.md) — Comprehensive technical reference and decision log.
- [DEPLOY.md](file:///c:/Users/USER/Documents/aletheia/DEPLOY.md) — Free-tier cloud deployment guide (Render, Neon, Upstash, Vercel).
- [learnings.md](file:///c:/Users/USER/Documents/aletheia/learnings.md) — First-principles engineering concepts, security deep dives, and interview talking points.
- [CHANGELOG.md](file:///c:/Users/USER/Documents/aletheia/CHANGELOG.md) — Release notes for v1.0.0.
