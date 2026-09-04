import logging
import os
import asyncio
from app.db.database import AsyncSessionLocal
from app.config import settings
from app.models.remediation import PatchStatus, RemediationJob
from app.models.audit import AuditLog
from app.services.git_applier import apply_unified_diff
from app.services.github_service import create_pull_request
from app.services.patcher import generate_patch

logger = logging.getLogger("aletheia")
job_limit = asyncio.Semaphore(settings.MAX_CONCURRENT_JOBS)

async def _record_audit_event(db, job_id: str | None, event_type: str, actor: str = "system", details: dict | None = None):
    try:
        audit = AuditLog(job_id=job_id, event_type=event_type, actor=actor, details=details or {})
        db.add(audit)
        await db.commit()
    except Exception as exc:
        logger.warning("Failed to record audit event %s for job %s: %s", event_type, job_id, exc)

async def _status(db, job_id: str, status: PatchStatus, error: str | None = None) -> None:
    try:
        job = await db.get(RemediationJob, job_id)
        if job:
            job.status = status
            if error:
                job.error_message = error
            await db.commit()
    except Exception as exc:
        try:
            await db.rollback()
        except Exception:
            pass
        logger.warning("Unable to update remediation job %s: %s", job_id, exc)

async def process_remediation_job(job_id: str, error_log: str, target_file: str, auto_approve: bool = False, max_retries: int = 2):
    """Executes the pipeline: GENERATING -> GENERATED -> DRY_RUN_PASSED -> (WAIT_FOR_APPROVAL / PR_CREATED).
    Supports exponential retries for transient failure handling and audit logging.
    """
    async with AsyncSessionLocal() as db:
        async with job_limit:
            attempt = 0
            while attempt <= max_retries:
                attempt += 1
                try:
                    await _record_audit_event(db, job_id, "PIPELINE_STARTED", details={"attempt": attempt, "target_file": target_file})
                    await _status(db, job_id, PatchStatus.GENERATING)
                    
                    patch, job = await generate_patch(db, error_log, target_file, job_id=job_id)
                    await _record_audit_event(db, job_id, "PATCH_GENERATED", details={"confidence": patch.confidence_score, "explanation": patch.explanation})
                    
                    repo_path = os.getenv("REPO_PATH", ".")
                    await apply_unified_diff(repo_path, patch.unified_diff, dry_run=True)
                    await _status(db, job.id, PatchStatus.DRY_RUN_PASSED)
                    await _record_audit_event(db, job_id, "DRY_RUN_PASSED", details={"repo_path": repo_path})

                    if auto_approve:
                        pr = await create_pull_request(
                            repo_path, job.id, patch.unified_diff,
                            "fix(autofix): resolve incident", patch.explanation
                        )
                        await _status(db, job.id, PatchStatus.PR_CREATED)
                        await _record_audit_event(db, job_id, "PR_CREATED", details={"pr_result": str(pr)})
                        return pr
                    else:
                        logger.info("Job %s validated dry-run. Awaiting human approval before creating PR.", job.id)
                        await _record_audit_event(db, job_id, "AWAITING_APPROVAL")
                        return {"status": "dry_run_passed", "job_id": job.id, "message": "Awaiting human review & approval"}
                        
                except Exception as exc:
                    logger.warning("Attempt %d for remediation job %s failed: %s", attempt, job_id, exc)
                    if attempt <= max_retries:
                        await asyncio.sleep(2 ** attempt)  # exponential backoff
                    else:
                        await _status(db, job_id, PatchStatus.FAILED, str(exc))
                        await _record_audit_event(db, job_id, "PIPELINE_FAILED", details={"error": str(exc)})
                        logger.error("Remediation job %s failed after %d attempts: %s", job_id, attempt, exc)
                        return {"status": "failed", "error": str(exc)}

async def approve_and_create_pr(job_id: str, actor: str = "on_call_engineer"):
    """Server-side approval endpoint execution gate."""
    async with AsyncSessionLocal() as db:
        job = await db.get(RemediationJob, job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")
        if job.status not in (PatchStatus.DRY_RUN_PASSED, PatchStatus.GENERATED):
            raise ValueError(f"Job {job_id} is in status {job.status}, cannot approve until dry-run passes")
        
        repo_path = os.getenv("REPO_PATH", ".")
        pr = await create_pull_request(
            repo_path, job.id, job.unified_diff,
            f"fix(autofix): resolve incident {job.id[:8]}", job.explanation or "Remediation patch approved"
        )
        await _status(db, job.id, PatchStatus.PR_CREATED)
        await _record_audit_event(db, job.id, "APPROVAL_GRANTED", actor=actor, details={"pr_result": str(pr)})
        return pr

async def reject_remediation_job(job_id: str, actor: str = "on_call_engineer", reason: str = "Rejected by reviewer"):
    """Server-side rejection endpoint."""
    async with AsyncSessionLocal() as db:
        job = await db.get(RemediationJob, job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")
        await _status(db, job.id, PatchStatus.FAILED, f"Rejected: {reason}")
        await _record_audit_event(db, job.id, "REJECTED", actor=actor, details={"reason": reason})
        return {"status": "rejected", "job_id": job_id}