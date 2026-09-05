"""
Approval, rejection, and audit activity endpoints.

These endpoints are the human-in-the-loop interface: an on-call engineer
uses the React UI (which calls these endpoints) to approve or reject a
patch after reviewing the diff in the DiffViewer.

All endpoints require authentication (`X-API-Key` header).
"""
import logging

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.audit import AuditLog
from app.security import require_api_key
from app.services.github_service import _sanitize_output
from app.services.orchestrator import approve_and_create_pr, reject_remediation_job

logger = logging.getLogger("aletheia")
router = APIRouter()


class ApprovalPayload(BaseModel):
    """Request body for the approve endpoint."""
    pass


class RejectionPayload(BaseModel):
    """Request body for the reject endpoint."""
    reason: str = "Rejected during review"
    pass


@router.post(
    "/jobs/{job_id}/approve",
    dependencies=[Depends(require_api_key)],
    summary="Approve a dry-run validated patch and create a GitHub PR",
)
async def approve_job(
    job_id: str,
    payload: ApprovalPayload = Body(default_factory=ApprovalPayload),
) -> dict:
    """Approve a patch that has passed dry-run validation.

    Creates a Git branch, commits the stored patch, pushes to remote,
    and opens a GitHub Pull Request. The job status moves to PR_CREATED.

    Only jobs in DRY_RUN_PASSED or WAIT_FOR_APPROVAL state can be approved.
    """
    try:
        pr_result = await approve_and_create_pr(job_id, actor="authenticated_operator")
        return {"status": "approved", "job_id": job_id, "pull_request": pr_result}
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        sanitized = _sanitize_output(str(exc))
        logger.error("Approval failed for job %s: %s", job_id, sanitized)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Approval failed: {sanitized}",
        )


@router.post(
    "/jobs/{job_id}/reject",
    dependencies=[Depends(require_api_key)],
    summary="Reject a patch and mark the job as FAILED",
)
async def reject_job(
    job_id: str,
    payload: RejectionPayload = Body(...),
) -> dict:
    """Reject a patch without creating a PR.

    Marks the job FAILED with the rejection reason. Records an audit event
    with the actor's identity and reason text.
    """
    try:
        return await reject_remediation_job(
            job_id, actor="authenticated_operator", reason=payload.reason
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        sanitized = _sanitize_output(str(exc))
        logger.error("Rejection failed for job %s: %s", job_id, sanitized)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Rejection failed: {sanitized}",
        )


@router.get(
    "/activity",
    dependencies=[Depends(require_api_key)],
    summary="Fetch recent audit log entries",
)
async def list_activity(
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Return the most recent audit log entries, newest first.

    Used by the React Activity Log screen to display the real-time
    security and operational event stream.
    """
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
    result = await db.execute(stmt)
    logs = result.scalars().all()
    return [
        {
            "id": log.id,
            "job_id": log.job_id,
            "event_type": log.event_type,
            "actor": log.actor,
            "details": log.details,
            "created_at": log.created_at.isoformat(),
        }
        for log in logs
    ]
