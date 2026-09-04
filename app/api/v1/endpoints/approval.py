from fastapi import APIRouter, Depends, HTTPException, Body, status
from pydantic import BaseModel
from sqlalchemy import select
from app.db.database import AsyncSessionLocal
from app.models.audit import AuditLog
from app.services.orchestrator import approve_and_create_pr, reject_remediation_job
from app.security import require_api_key

router = APIRouter()

class RejectionPayload(BaseModel):
    reason: str = "Rejected during review"
    actor: str = "on_call_engineer"

class ApprovalPayload(BaseModel):
    actor: str = "on_call_engineer"

@router.post("/jobs/{job_id}/approve", dependencies=[Depends(require_api_key)])
async def approve_job(job_id: str, payload: ApprovalPayload = Body(default=ApprovalPayload())):
    try:
        pr_result = await approve_and_create_pr(job_id, actor=payload.actor)
        return {"status": "approved", "job_id": job_id, "pull_request": pr_result}
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to approve job: {exc}")

@router.post("/jobs/{job_id}/reject", dependencies=[Depends(require_api_key)])
async def reject_job(job_id: str, payload: RejectionPayload = Body(...)):
    try:
        res = await reject_remediation_job(job_id, actor=payload.actor, reason=payload.reason)
        return res
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to reject job: {exc}")

@router.get("/activity", dependencies=[Depends(require_api_key)])
async def list_activity(limit: int = 50):
    async with AsyncSessionLocal() as db:
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
                "created_at": log.created_at.isoformat()
            }
            for log in logs
        ]
