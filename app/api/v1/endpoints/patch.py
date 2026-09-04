import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.schemas.api import (
    ErrorLogRequest, 
    RemediationResponse, 
    ApplyPatchRequest, 
    ApplyPatchResponse
)
from app.services.patcher import generate_patch
from app.services.git_applier import apply_unified_diff, PatchApplicationError
from app.models.remediation import RemediationJob, PatchStatus
from app.security import require_api_key

logger = logging.getLogger("aletheia")
router = APIRouter()

@router.post("/generate", response_model=RemediationResponse, dependencies=[Depends(require_api_key)])
async def generate_code_patch(
    payload: ErrorLogRequest,
    db: AsyncSession = Depends(get_db)
):
    try:
        patch_result, job = await generate_patch(
            db=db, 
            error_log=payload.error_log, 
            target_file=payload.target_file
        )
        return RemediationResponse(status="success", job_id=job.id, patch=patch_result)
    except Exception as e:
        logger.error(f"[API ERROR] Patch generation failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Patch generation failed: {str(e)}"
        )

@router.post("/apply", response_model=ApplyPatchResponse, dependencies=[Depends(require_api_key)])
async def apply_patch(
    payload: ApplyPatchRequest,
    db: AsyncSession = Depends(get_db)
):
    try:
        result = await apply_unified_diff(
            repo_root=payload.repo_root,
            unified_diff=payload.unified_diff,
            dry_run=payload.dry_run
        )
        
        # Safe update of DB status if DB is active
        if payload.job_id:
            try:
                job = await db.get(RemediationJob, payload.job_id)
                if job:
                    job.status = (
                        PatchStatus.DRY_RUN_PASSED if payload.dry_run else PatchStatus.APPLIED
                    )
                    await db.commit()
            except Exception as db_err:
                logger.warning(f"[DB SKIPPED] Unable to update job status: {db_err}")

        return ApplyPatchResponse(
            status=result["status"], 
            job_id=payload.job_id, 
            detail=result["detail"]
        )
    except PatchApplicationError as e:
        if payload.job_id:
            try:
                job = await db.get(RemediationJob, payload.job_id)
                if job:
                    job.status = PatchStatus.FAILED
                    job.error_message = str(e)
                    await db.commit()
            except Exception:
                pass
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"[API ERROR] Apply patch failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Patch application failed: {str(e)}"
        )
