# ALETHEIA Demo Pathway

## Purpose

This document describes the reliable local demo flow for ALETHEIA. Local demo mode uses a deterministic transaction fixture and does not call Gemini, so it consumes no model credits.

## 1. Start Infrastructure

From the repository root:

```powershell
docker compose up postgres redis -d
```

Verify:

```text
PostgreSQL: 127.0.0.1:5435
Redis:      127.0.0.1:6379
```

## 2. Start the Backend

In a separate terminal:

```powershell
uv run uvicorn app.main:app --port 8001 --reload
```

Check:

```text
http://127.0.0.1:8001/health
http://127.0.0.1:8001/ready
```

Expected health response:

```json
{"status":"ok","service":"ALETHEIA","version":"1.0.0"}
```

## 3. Start the Worker

In a separate terminal:

```powershell
uv run arq app.worker.WorkerSettings
```

The worker should report:

```text
Starting worker for 1 functions: process_remediation_job
```

Only one local ARQ worker should be running for the demo.

## 4. Start the Frontend

In a separate terminal:

```powershell
cd frontend
npm run dev -- --host localhost --port 5173
```

Open:

```text
http://localhost:5173/
```

## 5. Submit a Demo Alert

Open the ingest modal and enter:

Target file:

```text
transaction_service.py
```

Incident payload:

```text
AttributeError: 'NoneType' object has no attribute 'get' on line 42 during transaction fee calculation
```

Click **Ingest & Trigger Remediation**.

Because `DEMO_MODE=true`, this uses a deterministic fixture and does not call Gemini.

## 6. Expected Job Path

The job should move through these states:

```text
PENDING
  -> GENERATING
  -> GENERATED
  -> PATCH_APPLIED
  -> VALIDATION_PASSED
  -> WAIT_FOR_APPROVAL
```

The generated patch should target only:

```text
transaction_service.py
```

The fixture adds a guard before dividing by the discount tier.

## 7. Review the Patch

Open the incident and verify:

- The target file is `transaction_service.py`.
- A unified diff is visible.
- The patch is small and limited to the target file.
- Validation has passed.
- The approval button is enabled only after validation.

## 8. Test Rejection

Click **Reject Patch**, enter a reason, and confirm.

Expected result:

```text
FAILED
```

No pull request is created.

## 9. Test Simulated Approval

Submit another transaction alert and wait for `WAIT_FOR_APPROVAL`.

Click **Approve & Push PR**.

With no `GITHUB_TOKEN`, expected result:

```text
PR simulated
DEMO MODE - NO REAL PR CREATED
```

No real GitHub branch or pull request is created in this mode.

## 10. Verify Activity

Open the Activity screen and check for events such as:

```text
PIPELINE_STARTED
PATCH_GENERATED
PATCH_APPLIED
VALIDATION_PASSED
AWAITING_APPROVAL
APPROVAL_GRANTED
REJECTED
PR_CREATED
```

For simulated approval, `PR_CREATED` represents the completed simulated outcome and does not mean a real GitHub PR exists.

## 11. Troubleshooting

### Frontend says Failed to fetch

Check that the backend is running on port `8001` and the frontend is running at `http://localhost:5173`.

### Jobs return HTTP 500

Start the dependencies:

```powershell
docker compose up postgres redis -d
```

Then restart the backend so database compatibility upgrades run.

### Job stays at PENDING

The ARQ worker is not running or more than one stale worker is competing for the queue. Stop duplicate workers and start one:

```powershell
uv run arq app.worker.WorkerSettings
```

### Job stays at GENERATED

Check the worker terminal. The job must complete isolated validation before approval is allowed. Do not click approval while the status is `GENERATED`.

### Approval returns HTTP 400

Approval is allowed only for:

```text
VALIDATION_PASSED
DRY_RUN_PASSED
WAIT_FOR_APPROVAL
```

Refresh the incident and wait for validation to finish.

## 12. Credit-Saving Rule

Keep `DEMO_MODE=true` for the local video. Only set `DEMO_MODE=false` when intentionally testing the Gemini integration with a configured API key.

The deterministic fixture currently supports `transaction_service.py`. Other target files require additional fixtures or a real Gemini call.
