# ALETHEIA

ALETHEIA is a FastAPI-based incident remediation service. It accepts alerts, generates a unified diff with Gemini, validates the diff, and can create a GitHub pull request.

## Architecture

```text
Datadog / Prometheus / generic webhook
      |
      v
POST /api/v1/webhooks/ingest -> 202 + job_id
      |
      v
BackgroundTasks -> Gemini patch generation -> Git dry-run
      |
      v
  branch, commit, push -> GitHub pull request
```

PostgreSQL stores remediation jobs, generated diffs, execution state, and failure messages. The existing direct patch endpoints remain available alongside the end-to-end webhook workflow.

See [frontend_blueprint.md](frontend_blueprint.md) for the proposed frontend information architecture, review workflow, visual direction, responsive behavior, and backend contracts.

## Current capabilities

- FastAPI application with async SQLAlchemy and PostgreSQL/pgvector support.
- Patch generation through the Gemini API.
- Unified diff dry-run validation through Git CLI.
- Generic, Datadog-style, and Prometheus-style webhook ingestion.
- Background remediation processing with database status updates.
- Git branch creation, commit, push, and GitHub pull request creation.

## Run locally

Requirements:

- Python 3.13 or newer.
- `uv`.
- A PostgreSQL instance with the pgvector extension for persistent operation.
- Git credentials that can push to the configured repository.

Install dependencies and start the API:

```powershell
uv sync
uv run uvicorn app.main:app --reload
```

In a second terminal, start the frontend:

```powershell
Set-Location frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5174
```

The API is available at `http://127.0.0.1:8001` by default in the frontend integration. Set `VITE_API_BASE_URL` if your backend uses another port.

## Configuration

Set these values in `.env` or the process environment:

- `DATABASE_URL`: Async SQLAlchemy URL. Defaults to the local Docker PostgreSQL service.
- `GEMINI_API_KEY`: Required for patch generation.
- `GITHUB_TOKEN`: Required for pull request creation.
- `GITHUB_REPOSITORY`: Optional `owner/repository` value. If omitted, it is read from the repository's `origin` remote.
- `GITHUB_BASE_BRANCH`: Optional pull request base branch. Defaults to `main`.
- `REPO_PATH`: Optional repository path used by the background worker. Defaults to `.`.

Start PostgreSQL with:

```powershell
docker compose up -d postgres
```

## Endpoints

- `GET /health`: Service health check.
- `GET /ready`: Database readiness check. Returns HTTP `503` when PostgreSQL is unavailable.
- `POST /api/v1/patch/generate`: Generate a patch synchronously.
- `POST /api/v1/patch/apply`: Validate or apply a supplied unified diff.
- `POST /api/v1/webhooks/ingest`: Acknowledge an alert and start background remediation. Returns HTTP `202` with a generated `job_id`.
- `GET /api/v1/jobs/{job_id}`: Read the authenticated job state and failure details.
- `GET /api/v1/jobs?limit=50`: Read the latest authenticated jobs for the frontend queue.

Generic webhook example:

```json
{
  "error_log": "ZeroDivisionError in calculate_transaction_fee",
  "target_file": "transaction_service.py"
}
```

The webhook response is:

```json
{
  "status": "processing",
  "job_id": "..."
}
```

## Validation

```powershell
uv run python -m compileall -q app
uv run pytest -q
```

The focused webhook and orchestration tests can be run with `uv run pytest -q tests/test_webhook.py`.
