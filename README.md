# ALETHEIA ⚡

**ALETHEIA is a constrained incident-to-validated-patch workflow for portfolio demonstrations.**

It receives a controlled alert, generates a proposed patch, enforces an allowed target-file policy, applies the patch in an isolated temporary workspace, runs targeted validation, waits for human approval, and creates or reuses one GitHub PR. It is not currently a fully autonomous production remediation system.

The normal automated test suite uses deterministic fixtures and makes zero Gemini, GitHub, or external-service calls. Real integrations are opt-in. Without `GITHUB_TOKEN`, the API reports `DEMO MODE - NO REAL PR CREATED`; it does not fabricate a PR URL.

---

## 🏗️ Architecture at a Glance

```
                                  ┌─────────────────────────────┐
                                  │   Prometheus / Datadog /    │
                                  │       Custom Webhooks       │
                                  └──────────────┬──────────────┘
                                                 │ POST (HMAC-SHA256 verified)
                                                 ▼
                                  ┌─────────────────────────────┐
                                  │     FastAPI Gateway         │
                                  │  (Rate-limiting, Security)  │
                                  └──────────────┬──────────────┘
                                                 │ Enqueue Job
                                                 ▼
                                  ┌─────────────────────────────┐
                                  │     Redis Queue (ARQ)       │
                                  └──────────────┬──────────────┘
                                                 │ Async Pop
                                                 ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                   ARQ Worker Pipeline                                  │
│                                                                                        │
│  1. Gemini/fixture patch ─► 2. Isolated apply ─► 3. Targeted tests ─► 4. Approval ─► PR │
│     (Generate Diff)          (allowed target)      (pytest/checks)      (human)       │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

**Core Stack:**
- **Backend:** Python 3.13, FastAPI, SQLAlchemy 2.0 (Async), PostgreSQL (Neon compatible)
- **Task Queue:** ARQ (Async Redis Queue) + Redis (Upstash compatible)
- **AI Engine:** Google Gemini 2.0 Flash (Structured JSON output via `response_schema`)
- **Git Engine:** Temporary isolated checkouts + constrained `git apply` + targeted tests
- **Frontend:** React 18, TypeScript, Vite, TailwindCSS, Lucide Icons

---

## 🚀 Quick Start (Docker Compose)

The fastest way to spin up the full stack locally (Postgres + Redis + API + Worker + Frontend):

```bash
# 1. Clone & enter repository
git clone https://github.com/priyanshi-100506/aletheia.git
cd aletheia

# 2. Copy and configure secrets
cp .env.example .env

# 3. Start all services
docker compose up --build
```

| Service | Endpoint | Description |
|---------|----------|-------------|
| **Frontend UI** | [http://localhost:5174](http://localhost:5174) | Interactive dashboard & diff viewer |
| **API Documentation** | [http://localhost:8001/docs](http://localhost:8001/docs) | Interactive Swagger UI |
| **Health Probe** | [http://localhost:8001/health](http://localhost:8001/health) | Liveness & database/redis connectivity check |

---

## 💻 Local Development Setup

If you prefer running components directly on your host machine:

```bash
# 1. Start database & Redis via Docker
docker compose up postgres redis -d

# 2. Install Python dependencies
uv sync

# 3. Configure environment
cp .env.example .env

# 4. Terminal 1: Run FastAPI backend
uv run uvicorn app.main:app --reload --port 8001

# 5. Terminal 2: Run ARQ worker
uv run arq app.worker.WorkerSettings

# 6. Terminal 3: Run React frontend
cd frontend
npm install
npm run dev
```

---

## ☁️ Optional Free-Tier Demonstration Deployment

ALETHEIA can be deployed on free-tier infrastructure for demonstration purposes:

| Component | Provider | Setup Summary |
|-----------|----------|---------------|
| **Database** | **[Neon](https://neon.tech)** | Serverless PostgreSQL (`sslmode=require` auto-handled) |
| **Queue / Cache** | **[Upstash](https://upstash.com)** | Serverless Redis (`rediss://...`) |
| **Backend + Worker** | **[Render](https://render.com)** | Free Web Service with `RUN_WORKER_INPROCESS=true` |
| **Frontend UI** | **[Vercel](https://vercel.com)** | Free Vite React hosting with SPA rewrites |

📖 **Detailed step-by-step instructions:** See [**`DEPLOY.md`**](DEPLOY.md).

---

## 📡 Webhook Ingest Examples

ALETHEIA accepts alerts in 3 standardized formats:

### 1. Generic Error Payload
```bash
curl -X POST http://localhost:8001/api/v1/webhooks/ingest \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <YOUR_API_KEY>" \
  -d '{
    "error_log": "AttributeError: '\''NoneType'\'' object has no attribute '\''get'\'' on line 42",
    "target_file": "app/services/payment.py",
    "context": "Failed during user checkout webhook processing"
  }'
```

### 2. Prometheus Alertmanager
```bash
curl -X POST http://localhost:8001/api/v1/webhooks/ingest \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <YOUR_API_KEY>" \
  -d '{
    "alerts": [
      {
        "status": "firing",
        "labels": { "alertname": "High5xxErrorRate", "service": "api" },
        "annotations": {
          "description": "Uncaught KeyError: user_id in auth_service.py",
          "summary": "Service auth experiencing errors"
        }
      }
    ]
  }'
```

### 3. Datadog Alert
```bash
curl -X POST http://localhost:8001/api/v1/webhooks/ingest \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <YOUR_API_KEY>" \
  -d '{
    "event_type": "error",
    "title": "API Gateway 500 Spike",
    "body": "ZeroDivisionError: division by zero in calculate_metrics.py:88"
  }'
```

---

## 🧪 Testing Suite

ALETHEIA includes a comprehensive test suite with 100% mocked external I/O (no live database or Redis required for testing):

```bash
# Run pytest with short tracebacks
uv run pytest tests/ -v --tb=short
```

### Test Coverage Highlights
- `tests/test_security_webhooks.py`: Health probes, HMAC SHA256 signature verification, API key authentication, and async webhook ingestion.
- `tests/test_webhook.py`: Payload normalization across Prometheus/Datadog/Generic alerts, orchestrator pipeline execution, approval workflows, AI failure recovery, and validation error handling.

Run the controlled portfolio scenarios without external services:

```bash
uv run python scripts/run_scenario.py --all
uv run python scripts/run_scenario.py scenario-08
```

The catalog contains twelve scenarios, including unauthorized-file, path-traversal, prompt-injection, malformed-output, and duplicate-approval safe-failure cases.

### Real Portfolio Validation

Five small broken repositories exercise the actual patch safety and isolated-test path:

```bash
uv run python scripts/run_portfolio_validation.py SC-01
uv run python scripts/run_portfolio_validation.py SC-02
uv run python scripts/run_portfolio_validation.py SC-03
uv run python scripts/run_portfolio_validation.py SC-04
uv run python scripts/run_portfolio_validation.py SC-05
uv run python scripts/run_portfolio_validation.py --all
```

The runner uses deterministic fixture patches, so these commands make zero Gemini calls. It executes the baseline failing test, generates a constrained unified diff, rejects an unauthorized extra-file diff, applies the patch in a temporary workspace, runs the scenario's pytest command, records approval, and calls the real GitHub service. Without an explicitly configured token, the result is `DEMO MODE - NO REAL PR CREATED`.

### Security and Demo Modes

Protected mode is the default: set `API_KEY` and `WEBHOOK_SECRET`; missing credentials are rejected. For an explicitly local demonstration only, set `DEMO_MODE=true` with a non-production `ENVIRONMENT`. The frontend reads `VITE_API_KEY` and sends it as `X-API-Key` when configured.

### 🧪 Controlled Demo Run (ALETHEIA vs. Demo Bugs)

ALETHEIA includes a deterministic test suite and incident ingestion endpoint specifically wired for [`aletheia-demo-bugs`](https://github.com/priyanshi-100506/aletheia-demo-bugs).

Repository identity is part of the incident contract. ALETHEIA clones the
allowlisted `repository` into a new temporary checkout pinned to `base_sha`;
source context, validation, approval re-check, branch push, and PR verification
all use that checkout. `GITHUB_REPOSITORY` is not used as a fallback target.

1. **Verify Demo Repository Baseline (5 intentional bugs):**
   ```powershell
   .\scripts\verify_demo.ps1
   ```

2. **Ingest an Incident:**
   ```bash
   curl -X POST http://localhost:8000/api/v1/incidents \
     -H "Content-Type: application/json" \
     -d '{
       "repository": "priyanshi-100506/aletheia-demo-bugs",
       "base_sha": "0606c8c56c0f0319cf07d823adafa2be3aebbba6",
       "scenario": "scenario_1",
       "error_log": "AttributeError: NoneType object has no attribute upper in get_user_display_name"
     }'
   ```

3. **Pipeline Execution:**
   - Evaluates baseline target failure (`test_users.py::test_display_name_none`).
   - Clones the incident repository at its requested base SHA, then generates and applies a unified patch in an isolated workspace.
   - Re-tests target scenario (must pass).
   - Runs full regression suite to guarantee no unintentional breaks.
   - Requires operator approval before opening a PR (or simulates in `DEMO_MODE=true`). A real result is persisted only after GitHub verifies the repository, branch, commit, and PR fields; failures fail closed.

---

## 📁 Repository Structure

```
aletheia/
├── app/
│   ├── main.py                    # FastAPI application & lifespan management
│   ├── config.py                  # Pydantic Settings & environment validation
│   ├── security.py                # API key verification dependency
│   ├── worker.py                  # ARQ worker configuration & task registrations
│   ├── api/v1/endpoints/
│   │   ├── webhooks.py            # POST /webhooks/ingest (async job queueing)
│   │   ├── jobs.py                # GET /jobs, GET /jobs/{id}
│   │   ├── approval.py            # POST /jobs/{id}/approve|reject, GET /activity
│   │   └── patch.py               # POST /patch/generate|apply (direct synchronous)
│   ├── db/
│   │   └── database.py            # Async SQLAlchemy engine & Neon SSL handler
│   ├── models/
│   │   ├── remediation.py         # RemediationJob, PatchStatus, PatchType
│   │   └── audit.py               # AuditLog & action tracking
│   ├── schemas/
│   │   ├── webhook.py             # Inbound alert schemas & normalization logic
│   │   └── patch.py               # PatchResult Gemini structured schema
│   └── services/
│       ├── orchestrator.py        # End-to-end remediation pipeline coordinator
│       ├── patcher.py             # Gemini 2.0 Flash prompt engineering & generation
│       ├── git_applier.py         # Subprocess git apply --check & patch validation
│       ├── github_service.py      # Git worktree isolation & GitHub Pull Request API
│       ├── queue_service.py       # ARQ Redis queue enqueue helper
│       ├── redis_store.py         # Redis sliding-window rate limiter & idempotency
│       └── security_service.py    # HMAC SHA256 webhook signature verification
├── frontend/                      # Vite + React + TypeScript Dashboard
│   ├── src/                       # Components, DiffViewer, ActivityLog, API client
│   └── vercel.json                # Vercel SPA routing configuration
├── tests/                         # Pytest test suite with isolated mocking
├── render.yaml                    # Render Blueprint configuration
├── docker-compose.yml             # Full-stack local composition
├── DEPLOY.md                      # Free-tier cloud deployment guide
├── documentation.md               # Deep technical specification & decision log
└── CHANGELOG.md                   # v1.0.0 release notes
```

---

## 📖 Deep Technical Documentation

For complete architectural details, security models, data dictionaries, and design rationale:
- [**`documentation.md`**](documentation.md) — Exhaustive system reference & technical guide.
- [**`DEPLOY.md`**](DEPLOY.md) — Optional free-tier demonstration deployment guide.
- [**`CHANGELOG.md`**](CHANGELOG.md) — Version 1.0.0 release notes.

---

## 📄 License

Distributed under the MIT License. See `LICENSE` for more information.
