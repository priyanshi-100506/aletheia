from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.remediation import RemediationJob
from app.security import require_api_key

router = APIRouter()


def _job_response(job: RemediationJob) -> dict:
    return {
        "job_id": job.id,
        "status": job.status,
        "target_file": job.target_file,
        "error_message": job.error_message,
        "bug_description": job.bug_description,
        "explanation": job.explanation,
        "unified_diff": job.unified_diff,
        "confidence_score": job.confidence_score,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }


@router.get("", dependencies=[Depends(require_api_key)])
async def list_jobs(
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=100),
):
    result = await db.scalars(
        select(RemediationJob).order_by(RemediationJob.created_at.desc()).limit(limit)
    )
    return [_job_response(job) for job in result]


@router.get("/{job_id}", dependencies=[Depends(require_api_key)])
async def get_job_status(job_id: str, db: AsyncSession = Depends(get_db)):
    job = await db.get(RemediationJob, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return _job_response(job)