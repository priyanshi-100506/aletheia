# ALETHEIA Handover & Architecture Document

## 1. Project Summary

ALETHEIA is an autonomous AIOps incident remediation platform with a FastAPI backend and a React/Vite operational command center frontend. It ingests monitoring alerts (Datadog, Prometheus, generic webhooks), normalizes payloads, generates unified code diff patches using Google Gemini AI, validates patches inside isolated Git worktrees, and exposes a human-in-the-loop approval workflow to open GitHub Pull Requests.

The frontend is an operational command center built under the Orchid Noir design system (`frontend_blueprint.md`).

---

## 2. Production & Security Upgrades Delivered

The platform has been hardened from a prototype into an engineering-grade AIOps platform:

### Security & Ingestion Safeguards
- **HMAC SHA-256 Webhook Verification (`X-Hub-Signature-256`):** Prevents webhook spoofing by validating incoming payload signatures against `WEBHOOK_SECRET`.
- **Sliding-Window Rate Limiting:** Prevents Denial of Service (DoS) attacks on webhook endpoints.
- **Idempotency Key Verification (`X-Idempotency-Key`):** Prevents duplicate alert ingestion and redundant LLM generation calls.
- **Server-Side Approval Gate:** Created `POST /api/v1/jobs/{job_id}/approve` and `POST /api/v1/jobs/{job_id}/reject` endpoints. Automated code pushes cannot occur without explicit human authorization.

### Reliability & Audit Logging
- **Append-Only Audit Log (`audit_logs` table):** Tracks all pipeline lifecycle events (`WEBHOOK_INGEST`, `PATCH_GENERATED`, `DRY_RUN_PASSED`, `APPROVAL_GRANTED`, `REJECTED`, `PR_CREATED`) for auditability.
- **Exponential Backoff Retries:** Handles transient Gemini LLM or GitHub API rate-limits gracefully.
- **Model Upgrades:** Dynamic support for `gemini-3.6-flash` and context-aware patch generation using local source code definitions.

### Frontend Command Center (Orchid Noir System)
- **5 Operational Screens:**
  1. **Incidents:** Dense table displaying open incidents, confidence, age, and status.
  2. **Review Queue:** Safety-critical view filtered specifically for dry-run validated patches.
  3. **Repositories:** Displays Git connection health, worktree isolation status, and diff policy limits.
  4. **Activity:** Real-time audit log stream.
  5. **Settings:** Integration status, HMAC secrets, and concurrency limits.
- **Diff Viewer Component (`DiffViewer.tsx`):** Split/unified code diff viewer with line numbers, copy actions, patch size risk warnings, and approval/rejection modals.
- **Alert Ingestion Modal (`AlertIngestModal.tsx`):** UI component to simulate and ingest alert trace payloads directly from the browser.

### Containerization & Deployment
- **Full Multi-Container Setup (`docker-compose.yml`):** Runs PostgreSQL + pgvector, FastAPI Backend, and React (Nginx) Frontend in a single command (`docker compose up --build`).

---

## 3. Current Runtime Commands

| Component | Address | Start command |
| --- | --- | --- |
| FastAPI backend | `http://127.0.0.1:8001` | `uv run uvicorn app.main:app --host 127.0.0.1 --port 8001` |
| React frontend | `http://127.0.0.1:5174` | `Set-Location frontend; npx vite --host 127.0.0.1 --port 5174` |
| PostgreSQL/pgvector | `127.0.0.1:5435` | `docker compose up -d postgres` |
| Full Stack Docker | `http://127.0.0.1:5174` | `docker compose up --build` |

---

## 4. Environment Configuration (`.env`)

```env
DATABASE_URL=postgresql+asyncpg://aletheia_user:aletheia_password@127.0.0.1:5435/aletheia_db
GEMINI_API_KEY=your_gemini_api_key
GITHUB_TOKEN=your_github_personal_access_token
GITHUB_REPOSITORY=priyanshi-100506/aletheia
GITHUB_BASE_BRANCH=main
WEBHOOK_SECRET=your_hmac_secret
```

---

## 5. Automated Test & Verification Commands

Backend test suite:
```powershell
uv run python -m pytest tests/test_security_webhooks.py tests/test_webhook.py
uv run python -m compileall -q app
```

Frontend checks:
```powershell
Push-Location frontend
npx tsc -b --pretty false
npx vite build --logLevel error
npx oxlint src --format stylish
Pop-Location
```

---

## 6. Engineering Documentation & Learning Guide

Refer to [learnings.md](file:///c:/Users/USER/Documents/aletheia/learnings.md) for a first-principles technical breakdown of the architecture, security boundaries, and interview talking points for AI, DevOps, and Backend Engineering positions.
