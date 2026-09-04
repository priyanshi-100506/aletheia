# ALETHEIA Handover

## 1. Project Summary

ALETHEIA is an incident remediation platform with a FastAPI backend and a React/Vite frontend. It accepts monitoring alerts, normalizes them, generates a unified code diff with Gemini, validates the diff locally with Git, and can create a GitHub pull request.

The frontend is an operational incident command center. It is table-first, designed for on-call review, and follows the Orchid Noir design system documented in `frontend_blueprint.md`.

## 2. Current Runtime

| Component | Address | Start command |
| --- | --- | --- |
| FastAPI backend | `http://127.0.0.1:8001` | `uv run uvicorn app.main:app --host 127.0.0.1 --port 8001` |
| React frontend | `http://127.0.0.1:5174` | `Set-Location frontend; npm run dev -- --host 127.0.0.1 --port 5174` |
| PostgreSQL/pgvector | `127.0.0.1:5435` | `docker compose up -d postgres` |

The frontend API client defaults to `http://127.0.0.1:8001/api/v1`. Override it with `VITE_API_BASE_URL` before starting Vite.

## 3. Backend Delivered

### API and routing

- `GET /health` is a process liveness check.
- `GET /ready` checks database connectivity and returns `503` when unavailable.
- `POST /api/v1/patch/generate` generates and persists a patch.
- `POST /api/v1/patch/apply` validates or applies a supplied unified diff.
- `POST /api/v1/webhooks/ingest` accepts generic, Datadog-style, and Prometheus-style payloads and returns HTTP `202` with a job ID.
- `GET /api/v1/jobs?limit=50` lists recent remediation jobs.
- `GET /api/v1/jobs/{job_id}` returns one job and its remediation details.
- CORS allows configured frontend origins through `FRONTEND_ORIGINS`.

Mutation and job routes use `X-API-Key` when `API_KEY` is configured or when the environment is not development. The frontend intentionally does not embed an API key in its browser bundle.

### Alert normalization

`app/schemas/webhook.py` maps provider payloads to:

```text
GenericAlertPayload(error_log, target_file)
```

Generic payloads use `error_log` and optional `target_file`. Prometheus payloads prefer firing alerts and use annotation descriptions, summaries, or alert names. Datadog-style payloads use `message`, `body`, `error_log`, or `title`.

### Remediation pipeline

`app/services/orchestrator.py` executes:

```text
PENDING
  -> GENERATING
  -> GENERATED
  -> DRY_RUN_PASSED
  -> PR_CREATED
```

Any pipeline failure attempts to move the job to `FAILED` and stores the error message. Database status updates are best effort and do not mask the primary operation.

The job ID created by webhook ingestion is passed into patch generation so records and Git branches remain correlated.

### Safety and efficiency controls

- Error logs, patch bodies, and repository paths have configured size limits.
- Repository paths are restricted to the configured `REPO_PATH` checkout.
- Unified diff headers reject absolute paths and traversal paths such as `../`.
- Git subprocess calls have a 30-second timeout.
- Git and Gemini blocking operations are moved away from the async event loop.
- GitHub HTTP calls use explicit connect/read timeouts.
- Remediation concurrency is capped by `MAX_CONCURRENT_JOBS`.
- GitHub changes run in temporary detached worktrees instead of switching the shared checkout.
- API-key comparison uses constant-time comparison.
- Public readiness failures do not expose connection details.

These controls provide bounded and safer behavior. Zero latency cannot be guaranteed for database, LLM, Git, network, or GitHub operations.

## 4. Frontend Delivered

The frontend lives in `frontend/` and uses React, TypeScript, Vite, and Lucide icons.

Implemented UI behavior:

- Orchid Noir navigation rail with a text-only `ALETHEIA` wordmark.
- Incident command center as the first screen, without a marketing hero.
- Live incident table populated from `GET /api/v1/jobs?limit=50`.
- Search by incident ID, title, service, or file.
- Filters for all, review, generating, validated, and failed jobs.
- Incident detail drawer with status, confidence, summary, target file, branch, and activity timeline.
- Approval button disabled unless the job is validated.
- Backend connection indicator showing `Connecting`, `Production`, or `Demo data`.
- Demo data fallback when the backend is unreachable.
- 30-second polling with `AbortController` cleanup.
- Responsive navigation and mobile detail drawer.
- Accessible labels for icon-only controls and visible keyboard focus.

The frontend API adapter is `frontend/src/api.ts`. It supports jobs collection, single-job retrieval, and alert ingestion. The current command-center screen uses the jobs collection and is ready for the remaining mutation screens.

## 5. Design Decisions

- Orchid brand colors are reserved for identity and chrome. Functional status colors use separate success, caution, danger, and info tokens.
- Sunshine is used as a restrained confidence/highlight color, never as body text or a large background.
- Fraunces is reserved for the wordmark and page titles. IBM Plex Sans is used for UI text. IBM Plex Mono is used for code, IDs, branches, and paths.
- No gradients, decorative blobs, identical card shells, decorative load animations, or emoji icons.
- The wordmark has no stock icon beside it.
- The browser never receives a long-lived backend API key. Production auth should use secure HttpOnly sessions through a same-origin frontend or BFF.
- FastAPI `BackgroundTasks` are retained for the minimal local implementation. They are process-local and should be replaced with a durable queue for production retries and restart recovery.

## 6. Configuration

Set values in `.env` or the process environment:

- `DATABASE_URL`: Async PostgreSQL URL. Local Docker uses `postgresql+asyncpg://aletheia_user:aletheia_password@127.0.0.1:5435/aletheia_db`.
- `GEMINI_API_KEY`: Required for Gemini patch generation.
- `GITHUB_TOKEN`: Required for GitHub pull request creation.
- `GITHUB_REPOSITORY`: Optional `owner/repository`; otherwise parsed from Git `origin`.
- `GITHUB_BASE_BRANCH`: Pull request base branch, default `main`.
- `REPO_PATH`: Allowed local checkout, default `.`.
- `API_KEY`: Backend API key for protected routes.
- `ENVIRONMENT`: Development allows no API key by default; non-development requires one.
- `MAX_ERROR_LOG_LENGTH`: Maximum error-log size.
- `MAX_PATCH_LENGTH`: Maximum diff size.
- `MAX_CONCURRENT_JOBS`: Concurrent remediation limit.
- `FRONTEND_ORIGINS`: Comma-separated allowed browser origins.
- `VITE_API_BASE_URL`: Frontend-only API base override, default `http://127.0.0.1:8001/api/v1`.

Do not commit real credentials. The existing `.env` is local configuration and should remain private.

## 7. Testing and Verification

Backend focused tests:

```powershell
Push-Location 'C:\Users\USER\Documents\aletheia'
uv run pytest -q tests/test_webhook.py
uv run python -m compileall -q app
Pop-Location
```

Frontend checks:

```powershell
Push-Location 'C:\Users\USER\Documents\aletheia\frontend'
npx tsc -b --pretty false
npx vite build --logLevel error
npx oxlint src --format stylish
Pop-Location
```

Verified local result: four focused backend tests pass, the backend compiles, and the frontend TypeScript build, Vite production build, and source lint pass.

The broader repository test suite still contains an integration script that calls Gemini and expects a generated patch to match the current `transaction_service.py`; that script has failed when the generated hunk targets stale source context. It requires external service behavior and should be replaced with deterministic mocked tests.

## 8. Manual End-to-End Test

1. Start PostgreSQL:

```powershell
docker compose up -d postgres
```

2. Start the backend on port `8001`:

```powershell
uv run uvicorn app.main:app --host 127.0.0.1 --port 8001
```

3. Start the frontend on port `5174`:

```powershell
Set-Location frontend
npm run dev -- --host 127.0.0.1 --port 5174
```

4. Open `http://127.0.0.1:5174/`. A working database produces `Production` and live job counts. An unavailable database produces `Demo data` and preserves the UI shell.

5. For a real remediation test, configure Gemini, GitHub, Git identity, `REPO_PATH`, and a disposable repository. Submit a generic webhook:

```powershell
$body = @{ error_log = 'Test incident from ALETHEIA'; target_file = 'transaction_service.py' } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8001/api/v1/webhooks/ingest -ContentType 'application/json' -Body $body
```

6. Query the returned job ID:

```powershell
Invoke-RestMethod http://127.0.0.1:8001/api/v1/jobs/YOUR_JOB_ID
```

Never run the first full workflow against a production checkout or repository.

## 9. Known Limitations

- BackgroundTasks are not durable and do not survive process restarts.
- There is no migration system; startup currently initializes tables directly.
- GitHub PR creation has not been tested against a live remote in this workspace.
- The approval button is currently a frontend presentation gate; a production approval endpoint and server-side authorization policy are still required.
- There is no full audit log, cancellation endpoint, retry endpoint, or role-based user model.
- The browser command center does not yet submit new alerts from a UI form; alert ingestion is currently tested through the API.
- The database has duplicate legacy base/session modules that should be consolidated before production migration work.
- Real API data requires PostgreSQL. Without it, the frontend intentionally falls back to demo data.

## 10. Recommended Next Steps

1. Add a durable worker queue with retries, cancellation, and dead-letter handling.
2. Add server-side approval and authorization before GitHub writes.
3. Consolidate SQLAlchemy configuration and introduce Alembic migrations.
4. Add deterministic Git worktree and GitHub client integration tests.
5. Add webhook signature verification, replay protection, idempotency keys, and rate limiting.
6. Add repository and job audit events for the frontend activity screen.
7. Add frontend patch review, approval, retry, repository, activity, and settings screens.
8. Add production session authentication through a same-origin BFF.
