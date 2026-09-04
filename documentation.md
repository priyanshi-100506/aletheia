# ALETHEIA Technical Documentation

## System Blueprint

ALETHEIA follows this execution topology:

```text
Alert and telemetry sources
        -> FastAPI ingestion and routing
        -> HTTP 202 with job_id
        -> FastAPI background remediation task
        -> Gemini patch generation
        -> local Git dry-run validation
        -> branch, commit, and push
        -> GitHub REST API pull request
```

Supported source categories are generic HTTP payloads, Datadog-style alerts, and Prometheus-style alert groups. PostgreSQL stores the remediation job record, generated diff, execution state, and failure message.

## Module Tree

```text
app/
    api/v1/endpoints/patch.py       Patch generation and application endpoints
    api/v1/endpoints/webhooks.py    Alert normalization and ingestion endpoint
    api/v1/router.py                v1 route aggregator
    config.py                       Environment and settings configuration
    db/database.py                  Async SQLAlchemy engine and sessions
    models/remediation.py           Remediation ORM model and PatchStatus
    schemas/webhook.py              Vendor payload normalization
    services/patcher.py             Gemini patch generation
    services/git_applier.py         Local unified diff validation/application
    services/github_service.py      Git push and GitHub PR creation
    services/orchestrator.py        End-to-end background remediation worker
    api/v1/endpoints/jobs.py        Authenticated job status endpoint
    main.py                         FastAPI application and lifecycle
```

## Architecture

The API is mounted in `app/main.py` with the `/api/v1` prefix. The v1 router includes patch endpoints and webhook endpoints. Database access uses `AsyncSessionLocal` from `app/db/database.py`.

The remediation pipeline is implemented in `app/services/orchestrator.py`:

```text
webhook payload
    -> normalize_alert
    -> background task
    -> generate_patch
    -> apply_unified_diff(dry_run=True)
    -> create_pull_request
```

## Data Flow

1. The webhook normalizes a provider payload into `(error_log, target_file)`.
2. A job ID is generated and returned immediately with HTTP `202`.
3. The background task persists the job and moves it through `GENERATING`.
4. Gemini produces the root-cause description and unified diff.
5. `git apply --check` validates the diff, with the existing three-way fallback.
6. Git creates `fix/aletheia-{job_id}`, applies and commits the diff, then pushes it.
7. GitHub receives `POST /repos/{owner}/{repo}/pulls` and returns the PR URL.

The job lifecycle is `PENDING -> GENERATING -> GENERATED -> DRY_RUN_PASSED -> PR_CREATED`. Any failed pipeline operation attempts to set `FAILED` and stores the error text.

## Configuration Reference

| Variable | Purpose | Default |
| --- | --- | --- |
| `DATABASE_URL` | Async PostgreSQL connection string | Local Docker PostgreSQL URL |
| `GEMINI_API_KEY` | Gemini authentication | Empty, generation fails |
| `GITHUB_TOKEN` | GitHub API authentication | Unset, PR creation fails |
| `GITHUB_REPOSITORY` | GitHub `owner/repository` | Parsed from `origin` |
| `GITHUB_BASE_BRANCH` | Pull request target branch | `main` |
| `REPO_PATH` | Local checkout used by the worker | `.` |

## Payload normalization

`GenericAlertPayload` is the canonical internal shape:

- `error_log: str`
- `target_file: str | None`

Payloads containing `alerts` are interpreted as Prometheus-style payloads. Firing alerts are preferred, and descriptions, summaries, or alert names are combined into the error log. Payloads containing `error_log` are treated as generic. Other payloads are interpreted as Datadog-style and use `message`, `body`, `error_log`, or `title` in that order.

The webhook accepts a dictionary body to support multiple provider formats. Provider-specific validation is intentionally lightweight and unknown fields are allowed for Datadog and Prometheus payloads.

## Job state decisions

`PatchStatus` includes the following workflow states:

- `PENDING`: Initial persisted state.
- `GENERATING`: Patch generation has started.
- `GENERATED`: Gemini returned and the patch was stored.
- `DRY_RUN_PASSED`: The unified diff validated successfully.
- `PR_CREATED`: GitHub returned a created pull request.
- `FAILED`: A pipeline operation failed.

`APPLIED` remains available for the existing direct patch endpoint. The orchestrator does not apply changes directly to the working tree after dry-run; it creates a branch and applies the patch as part of PR creation.

## GitHub decisions

The Git service uses Git CLI because the repository checkout, patch application, commit, and push are local operations. The branch is normalized to `fix/aletheia-{job_id}`. The commit message is fixed as `fix(autofix): resolve incident`.

The GitHub API repository is taken from `GITHUB_REPOSITORY` when supplied. Otherwise, the service parses the `origin` remote. The pull request base branch is `GITHUB_BASE_BRANCH` or `main`. The result includes `pr_url`, `url`, `number`, and the raw API response.

## Failure handling

Database status updates are best effort. A failed lookup, commit, or rollback is logged and does not mask the primary remediation operation. Pipeline failures are recorded as `FAILED` when the job record can be updated, then returned by the background task as a failure result.

The current API returns immediately from webhook ingestion. FastAPI `BackgroundTasks` are process-local and are suitable for the current minimal implementation, but a durable queue is recommended when retries, persistence across restarts, or parallel worker scaling are required.

`/health` is a liveness check. `/ready` performs a lightweight database check and returns `503` when the service cannot use PostgreSQL. Mutation and job routes require `X-API-Key` when `API_KEY` is configured or when the environment is not development.

## Verification status

The application compiles successfully with `uv run python -m compileall -q app`. Route registration and generic, Datadog-style, and Prometheus-style normalization were verified, and `uv run pytest -q tests/test_webhook.py` passes four isolated webhook and orchestrator tests. The frontend passes TypeScript compilation, Vite production build, and Oxlint. Git and GitHub operations have not been exercised against a live remote in this workspace.

## Implementation Checklist

- [x] FastAPI route mounting for patch and webhook workflows.
- [x] Graceful database fallback and best-effort status updates.
- [x] Gemini-based unified diff generation.
- [x] Git strict check and three-way fallback.
- [x] Multi-vendor telemetry normalization.
- [x] GitHub branch, push, and pull request automation.
- [x] Background orchestration through FastAPI `BackgroundTasks`.
- [ ] Durable queue, retries, and broader integration tests.

## Frontend Integration

The React frontend lives in `frontend/` and starts with `npm run dev -- --host 127.0.0.1 --port 5174`. By default it connects to `http://127.0.0.1:8001/api/v1`, reads `GET /api/v1/jobs?limit=50`, and maps `PENDING`, `GENERATING`, `GENERATED`, `DRY_RUN_PASSED`, `PR_CREATED`, and `FAILED` into the command-center status labels. It polls the collection every 30 seconds and uses the existing demo incidents only when the backend cannot be reached.

Set `VITE_API_BASE_URL` to override the default `http://127.0.0.1:8000/api/v1`. The frontend deliberately does not accept `VITE_API_KEY`, because a Vite environment value becomes browser-visible. Production authentication should use a secure session cookie through a same-origin frontend or a backend-for-frontend proxy. The backend allows the Vite origins through `FRONTEND_ORIGINS`.
