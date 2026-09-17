import logging
from typing import Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.constants import SCENARIO_TO_TEST, SCENARIO_TARGET_FILES
from app.db.database import get_db
from app.models.remediation import RemediationJob, PatchStatus
from app.models.audit import AuditLog
from app.services.queue_service import enqueue_remediation_job

logger = logging.getLogger("aletheia")
router = APIRouter(tags=["Incident Ingestion"])


class IncidentIngestRequest(BaseModel):
    repository: str = Field(..., description="Target repository, e.g. priyanshi-100506/aletheia-demo-bugs")
    base_sha: Optional[str] = Field(None, min_length=7, max_length=64, description="Immutable commit SHA to remediate")
    error_log: str = Field(..., description="Raw incident traceback or error log")
    scenario: Optional[str] = Field(None, description="Predefined scenario identifier (e.g. scenario_1)")
    target_file: Optional[str] = Field(None, description="Optional target file path hint")
    target_test: Optional[str] = Field(None, description="Optional specific test identifier")
    auto_approve: bool = Field(False, description="Whether to auto approve upon passing validation")


class IncidentIngestResponse(BaseModel):
    status: str
    job_id: str
    scenario: Optional[str] = None
    target_test: Optional[str] = None
    target_file: Optional[str] = None
    message: str


@router.post("/incidents", response_model=IncidentIngestResponse, status_code=status.HTTP_202_ACCEPTED)
async def ingest_incident(
    payload: IncidentIngestRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    # 1. Validate repository allowlist
    normalized_repo = payload.repository.strip().removesuffix(".git").lower()
    allowed_norm = [r.strip().removesuffix(".git").lower() for r in settings.ALLOWED_REPOS]

    if normalized_repo not in allowed_norm:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Repository '{payload.repository}' is not authorized. Allowed repos: {settings.ALLOWED_REPOS}",
        )

    # 2. Determine target test & target file deterministically if scenario is given
    target_test = payload.target_test
    target_file = payload.target_file

    if payload.scenario:
        if payload.scenario not in SCENARIO_TO_TEST:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown scenario '{payload.scenario}'. Supported: {list(SCENARIO_TO_TEST.keys())}",
            )
        target_test = SCENARIO_TO_TEST[payload.scenario]
        if not target_file:
            target_file = SCENARIO_TARGET_FILES.get(payload.scenario)

    if not target_test:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either 'scenario' or explicit 'target_test' must be specified for controlled validation.",
        )

    # 3. Create persisted RemediationJob

    job = RemediationJob(
        error_log=payload.error_log,
        target_file=target_file,
        target_test=target_test,
        repository=payload.repository,
        base_sha=payload.base_sha,
        status=PatchStatus.PENDING,
    )
    db.add(job)
    await db.flush()

    # 4. Audit Log entry
    audit = AuditLog(
        job_id=job.id,
        event_type="INCIDENT_INGESTED",
        actor="api",
        details={
            "repository": payload.repository,
            "base_sha": payload.base_sha,
            "scenario": payload.scenario,
            "target_test": target_test,
            "target_file": target_file,
        },
    )
    db.add(audit)
    await db.commit()
    await db.refresh(job)

    # 5. Enqueue background task via ARQ / Redis
    redis_pool = getattr(request.app.state, "redis", None)
    try:
        await enqueue_remediation_job(
            redis=redis_pool,
            job_id=job.id,
            error_log=payload.error_log,
            target_file=target_file or "",
            auto_approve=payload.auto_approve,
        )
    except Exception as exc:
        logger.warning("Could not enqueue to Redis (%s). Job recorded as PENDING in DB.", exc)

    return IncidentIngestResponse(
        status="accepted",
        job_id=job.id,
        scenario=payload.scenario,
        target_test=target_test,
        target_file=target_file,
        message="Incident accepted and scheduled for remediation.",
    )
