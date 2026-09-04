import uuid
from fastapi import APIRouter, BackgroundTasks, Body, Depends, Header, HTTPException, Request, status

from app.schemas.webhook import normalize_alert
from app.services.orchestrator import process_remediation_job
from app.services.security_service import verify_webhook_signature, check_idempotency_key, check_rate_limit
from app.security import require_api_key

router = APIRouter()

@router.post("/ingest", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(require_api_key)])
async def ingest_alert(
    request: Request,
    background_tasks: BackgroundTasks,
    payload: dict = Body(..., max_length=200_000),
    x_hub_signature: str | None = Header(None, alias="X-Hub-Signature-256"),
    x_idempotency_key: str | None = Header(None, alias="X-Idempotency-Key"),
):
    # 1. Rate Limiting
    client_ip = request.client.host if request.client else "unknown"
    if not check_rate_limit(client_ip):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Rate limit exceeded. Try again in 60s.")

    # 2. Webhook Signature Verification
    body_bytes = await request.body()
    if not verify_webhook_signature(body_bytes, x_hub_signature):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook signature")

    # 3. Idempotency Check
    if x_idempotency_key:
        if not check_idempotency_key(x_idempotency_key):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Duplicate webhook payload received (idempotency key match)")

    normalized = normalize_alert(payload)
    job_id = str(uuid.uuid4())
    background_tasks.add_task(
        process_remediation_job, job_id, normalized.error_log, normalized.target_file or ""
    )
    return {"status": "processing", "job_id": job_id}