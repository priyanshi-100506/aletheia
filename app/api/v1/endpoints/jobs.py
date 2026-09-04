"""
Job status and listing endpoints.

Provides read-only access to RemediationJob records. Used by the React
Incident Command Center to display job status, diffs, and metadata.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.remediation import RemediationJob
from app.security import require_api_key

router = APIRouter()


def _serialize_job(job: RemediationJob) -> dict:
    """Convert a RemediationJob ORM instance to a JSON-safe dict.

    Datetimes are serialized to ISO 8601 strings. All other fields are
    returned as-is. Enum values are returned as their string representation.
    """
    return {
        "job_id": job.id,
        "status": job.status.value if job.status else None,
        "target_file": job.target_file,
        "error_message": job.error_message,
        "bug_description": job.bug_description,
        "explanation": job.explanation,
        "unified_diff": job.unified_diff,
        "confidence_score": job.confidence_score,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
    }


@router.get(
    "",
    dependencies=[Depends(require_api_key)],
    summary="List remediation jobs, newest first",
)
async def list_jobs(
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=100),
) -> list[dict]:
    """Return the most recent remediation jobs.

    Used by the Incident Command Center table. Jobs are ordered by
    `created_at` descending so the newest incident appears first.
    """
    result = await db.scalars(
        select(RemediationJob)
        .order_by(RemediationJob.created_at.desc())
        .limit(limit)
    )
    return [_serialize_job(job) for job in result]


@router.get(
    "/{job_id}",
    dependencies=[Depends(require_api_key)],
    summary="Fetch a single remediation job by ID",
)
async def get_job(job_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    """Return full detail for a single remediation job.

    Used by the DiffViewer to load the stored unified diff, confidence
    score, and explanation for human review.
    """
    job = await db.get(RemediationJob, job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found.",
        )
    return _serialize_job(job)