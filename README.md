# ALETHEIA ⚡

**Autonomous AIOps Platform — AI-Driven Incident Detection & Code Remediation.**

ALETHEIA listens to incoming production monitoring alerts (Prometheus, Datadog, or Generic JSON), analyzes the root cause with Google Gemini 2.0 Flash, generates an exact patch, validates it with a git conflict dry-run (`git apply --check`), and creates a GitHub Pull Request — with full human-in-the-loop approval or automated remediation.

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
│  1. Gemini 2.0 Flash ────► 2. Git Dry-Run ────► 3. Human Approval ────► 4. GitHub PR   │
│     (Generate Diff)          (git apply --check)   (React Diff Viewer)     (Worktree)  │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

**Core Stack:**
- **Backend:** Python 3.13, FastAPI, SQLAlchemy 2.0 (Async), PostgreSQL (Neon compatible)
- **Task Queue:** ARQ (Async Redis Queue) + Redis (Upstash compatible)
- **AI Engine:** Google Gemini 2.0 Flash (Structured JSON output via `response_schema`)
- **Git Engine:** Isolated Git Worktrees + Subprocess `git apply --check`
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

## ☁️ 100% Free-Tier Cloud Deployment

Deploy ALETHEIA completely free with **$0/month** infrastructure:

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
- `tests/test_webhook.py`: Payload normalization across Prometheus/Datadog/Generic alerts, orchestrator pipeline execution, auto-approval workflows, AI failure recovery, and dry-run validation error handling.

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
- [**`DEPLOY.md`**](DEPLOY.md) — 100% Free-Tier Cloud Deployment Guide.
- [**`CHANGELOG.md`**](CHANGELOG.md) — Version 1.0.0 release notes.

---

## 📄 License

Distributed under the MIT License. See `LICENSE` for more information.
