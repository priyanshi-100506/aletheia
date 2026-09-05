"""
Alert ingestion endpoint.

Receives alert payloads from external monitoring systems (Datadog, Prometheus,
or any generic HTTP webhook), validates them, and enqueues a remediation job.

Security gates (in order):
    1. Rate limiting   — Redis sliding-window, 30 req/min per IP (configurable)
    2. HMAC signature  — sha256= prefix, verified against WEBHOOK_SECRET
    3. Idempotency     — X-Idempotency-Key header, 1-hour dedup window

Response: HTTP 202 Accepted with {status, job_id} — the job runs asynchronously
in the ARQ worker process, not inside this request.
"""
import logging
import uuid

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request, status

from app.db.database import AsyncSessionLocal
from app.models.remediation import PatchStatus, RemediationJob
from app.schemas.webhook import normalize_alert
from app.security import require_api_key
from app.services.queue_service import enqueue_remediation_job
from app.services.redis_store import check_idempotency_key, check_rate_limit
from app.services.security_service import verify_webhook_signature

logger = logging.getLogger("aletheia")
router = APIRouter()


@router.post(
    "/ingest",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_api_key)],
    summary="Ingest an alert and enqueue a remediation job",
    response_description="Job accepted for asynchronous processing",
)
async def ingest_alert(
    request: Request,
    payload: dict = Body(..., max_length=200_000),
    x_hub_signature: str | None = Header(None, alias="X-Hub-Signature-256"),
    x_idempotency_key: str | None = Header(None, alias="X-Idempotency-Key"),
) -> dict:
    """Accept an alert payload and queue it for AI-driven remediation.

    Returns immediately with HTTP 202. The actual patch generation,
    dry-run validation, and PR creation happen in the ARQ worker process.

    **Headers:**
    - `X-API-Key` — required unless ENVIRONMENT=development and API_KEY is unset
    - `X-Hub-Signature-256` — required outside explicit demo mode
    - `X-Idempotency-Key` — optional deduplication key (prevents double-processing)

    **Body:** Any of:
    - Generic: `{"error_log": "...", "target_file": "app.py"}`
    - Prometheus Alertmanager webhook payload
    - Datadog webhook payload
    """
    client_ip = request.client.host if request.client else "unknown"

    # ── 1. Rate limiting ──────────────────────────────────────────────────────
    if not await check_rate_limit(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Try again in 60 seconds.",
        )

    # ── 2. HMAC signature verification ────────────────────────────────────────
    body_bytes = await request.body()
    if not verify_webhook_signature(body_bytes, x_hub_signature):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature. Check your WEBHOOK_SECRET configuration.",
        )

    # ── 3. Idempotency check ──────────────────────────────────────────────────
    if x_idempotency_key:
        if not await check_idempotency_key(x_idempotency_key):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Duplicate request: this idempotency key was already processed.",
            )

    # ── 4. Normalize alert payload ────────────────────────────────────────────
    normalized = normalize_alert(payload)
    job_id = str(uuid.uuid4())

    # ── 5. Pre-create DB record so GET /jobs/{id} returns immediately ─────────
    async with AsyncSessionLocal() as db:
        job = RemediationJob(
            id=job_id,
            error_log=normalized.error_log,
            target_file=normalized.target_file or "",
            status=PatchStatus.PENDING,
        )
        db.add(job)
        await db.commit()

    # ── 6. Enqueue to ARQ (Redis) ─────────────────────────────────────────────
    redis = request.app.state.redis
    await enqueue_remediation_job(
        redis=redis,
        job_id=job_id,
        error_log=normalized.error_log,
        target_file=normalized.target_file or "",
    )

    logger.info("Job %s enqueued for file=%s ip=%s", job_id, normalized.target_file, client_ip)
    return {"status": "processing", "job_id": job_id}