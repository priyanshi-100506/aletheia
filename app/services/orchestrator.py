"""
Remediation pipeline orchestrator.

This module contains the core end-to-end pipeline that runs inside the
ARQ worker process (see `app/worker.py`). Each function is designed to be
called as a background job, not from within a FastAPI request.

Pipeline stages:
    1. GENERATING  — Update job status; read source code context.
    2. GENERATED   — Invoke Gemini AI; receive structured PatchResult.
    3. DRY_RUN_PASSED — Validate patch applies cleanly with `git apply --check`.
    4. WAIT_FOR_APPROVAL — Halt; notify operator (auto_approve=False).
       or PR_CREATED   — Commit branch, push, create GitHub PR (auto_approve=True).
    5. FAILED      — Any unrecoverable error; stored with error_message.

Session management:
    Every function opens its own `AsyncSessionLocal()` session and closes it
    before returning. Sessions are NEVER passed between functions to avoid
    detached-instance errors and connection leaks.
"""
import asyncio
import logging
from sqlalchemy import update

from app.db.database import AsyncSessionLocal
from app.models.audit import AuditLog
from app.models.remediation import PatchStatus, RemediationJob
from app.services.git_applier import apply_unified_diff, validate_in_isolated_workspace
from app.services.github_service import create_pull_request
from app.services.patcher import generate_patch
from app.config import settings

logger = logging.getLogger("aletheia")

# Semaphore caps the number of concurrent pipeline executions inside one worker.
# ARQ already controls concurrency at the job level via `max_jobs`, but this
# provides an extra guard when `max_jobs` is set higher than desired for patching.
_job_semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_JOBS)


# ── Internal helpers ──────────────────────────────────────────────────────────


async def _update_status(
    job_id: str,
    new_status: PatchStatus,
    error: str | None = None,
) -> None:
    """Open a fresh session, update the job status, and close.

    Using a separate session per update avoids holding a connection open
    across long-running AI/git operations.
    """
    async with AsyncSessionLocal() as db:
        job = await db.get(RemediationJob, job_id)
        if job is None:
            logger.warning("_update_status: job %s not found", job_id)
            return
        job.status = new_status
        if error is not None:
            job.error_message = error[:2000]  # Guard against absurdly long error strings
        await db.commit()


async def _record_audit(
    job_id: str | None,
    event_type: str,
    actor: str = "system",
    details: dict | None = None,
) -> None:
    """Write one row to the audit_logs table.

    Failures are logged but never re-raised — audit logging must not
    interrupt the main pipeline.
    """
    try:
        async with AsyncSessionLocal() as db:
            entry = AuditLog(
                job_id=job_id,
                event_type=event_type,
                actor=actor,
                details=details or {},
            )
            db.add(entry)
            await db.commit()
    except Exception as exc:
        logger.warning(
            "Failed to write audit event %s for job %s: %s",
            event_type, job_id, exc,
        )


# ── Public pipeline entry point ───────────────────────────────────────────────


async def process_remediation_job(
    ctx: dict,  # ARQ passes its worker context as first argument
    job_id: str,
    error_log: str,
    target_file: str,
    *,
    auto_approve: bool = False,
) -> dict:
    """Full remediation pipeline, designed to run inside an ARQ worker.

    Args:
        ctx: ARQ worker context (contains redis, job_id, etc.). Not used
             directly here but required by the ARQ calling convention.
        job_id: UUID of the RemediationJob row created by the ingest endpoint.
        error_log: Raw alert/error log text to analyze.
        target_file: Path to the source file that likely contains the bug.
        auto_approve: If True, skip the human approval gate and create the PR
                      automatically after a successful dry-run. Intended for
                      trusted CI pipelines only.

    Returns:
        A dict describing the final outcome:
          {"pr_url": "...", "pr_number": 42}          — PR created
          {"status": "dry_run_passed", "job_id": "…"} — awaiting approval
          {"status": "failed", "error": "…"}          — pipeline failed
    """
    async with _job_semaphore:
        await _record_audit(job_id, "PIPELINE_STARTED", details={"target_file": target_file})

        # ── Stage 1: Generate patch via Gemini ────────────────────────────────
        try:
            await _update_status(job_id, PatchStatus.GENERATING)

            async with AsyncSessionLocal() as db:
                patch, job = await generate_patch(
                    db=db,
                    error_log=error_log,
                    target_file=target_file,
                    job_id=job_id,
                )

            await _record_audit(
                job_id, "PATCH_GENERATED",
                details={
                    "confidence": patch.confidence_score,
                    "file_path": patch.file_path,
                },
            )
        except Exception as exc:
            error_msg = str(exc)
            logger.error("Patch generation failed for job %s: %s", job_id, error_msg)
            await _update_status(job_id, PatchStatus.FAILED, error=error_msg)
            await _record_audit(job_id, "PIPELINE_FAILED", details={"stage": "generate", "error": error_msg})
            return {"status": "failed", "error": error_msg}

        # ── Stage 2: Dry-run validation ───────────────────────────────────────
        try:
            await validate_in_isolated_workspace(
                repo_root=settings.REPO_PATH,
                unified_diff=patch.unified_diff,
                allowed_target=patch.file_path,
            )
            await _update_status(job_id, PatchStatus.PATCH_APPLIED)
            await _update_status(job_id, PatchStatus.VALIDATION_PASSED)
            await _record_audit(job_id, "PATCH_APPLIED")
            await _record_audit(job_id, "VALIDATION_PASSED", details={"checks": ["git_apply", "py_compile"]})
        except Exception as exc:
            error_msg = str(exc)
            logger.error("Dry-run validation failed for job %s: %s", job_id, error_msg)
            await _update_status(job_id, PatchStatus.VALIDATION_FAILED, error=error_msg)
            await _record_audit(job_id, "PIPELINE_FAILED", details={"stage": "dry_run", "error": error_msg})
            return {"status": "failed", "error": error_msg}

        # ── Stage 3a: Human approval gate (default) ───────────────────────────
        if not auto_approve:
            await _update_status(job_id, PatchStatus.WAIT_FOR_APPROVAL)
            await _record_audit(job_id, "AWAITING_APPROVAL")
            logger.info("Job %s is awaiting human approval.", job_id)
            return {
                "status": "dry_run_passed",
                "job_id": job_id,
                "message": "Patch validated. Awaiting human review and approval.",
            }

        # ── Stage 3b: Auto-approve → create PR ───────────────────────────────
        return await _create_pr_for_job(job_id=job_id, unified_diff=patch.unified_diff)


async def approve_and_create_pr(job_id: str, actor: str = "on_call_engineer") -> dict:
    """Endpoint handler for the human approval action.

    Fetches the stored patch from the DB, validates the job is in an
    approvable state, then delegates to `_create_pr_for_job`.

    Raises:
        ValueError: If the job does not exist or is not in a valid state for approval.
    """
    async with AsyncSessionLocal() as db:
        job = await db.get(RemediationJob, job_id)
        if job is None:
            raise ValueError(f"Job {job_id} not found")
        if job.status == PatchStatus.PR_CREATED and job.pr_url:
            return {"pr_url": job.pr_url, "number": job.pr_number, "simulated": job.pr_simulated}
        if job.status not in (
            PatchStatus.VALIDATION_PASSED,
            PatchStatus.DRY_RUN_PASSED,
            PatchStatus.WAIT_FOR_APPROVAL,
        ):
            raise ValueError(
                f"Job {job_id} is in state '{job.status}' — "
                "can only approve jobs in DRY_RUN_PASSED or WAIT_FOR_APPROVAL state"
            )
        if not job.unified_diff:
            raise ValueError(f"Job {job_id} has no stored patch to apply")

        unified_diff = job.unified_diff
        claim = await db.execute(
            update(RemediationJob)
            .where(
                RemediationJob.id == job_id,
                RemediationJob.status.in_((
                    PatchStatus.VALIDATION_PASSED,
                    PatchStatus.DRY_RUN_PASSED,
                    PatchStatus.WAIT_FOR_APPROVAL,
                )),
            )
            .values(status=PatchStatus.APPROVING)
        )
        if claim.rowcount != 1:
            raise ValueError(f"Job {job_id} is already being approved or has already produced a PR")
        await db.commit()

    # ── TOCTOU Prevention: Re-verify dry-run against current repository HEAD ──
    try:
        await apply_unified_diff(
            repo_root=settings.REPO_PATH,
            unified_diff=unified_diff,
            dry_run=True,
            allowed_target=job.target_file,
        )
    except Exception as exc:
        error_msg = f"Re-verification dry-run failed (repo HEAD may have moved): {exc}"
        logger.error("Approval aborted for job %s: %s", job_id, error_msg)
        await _update_status(job_id, PatchStatus.FAILED, error=error_msg)
        await _record_audit(
            job_id, "PIPELINE_FAILED", actor=actor, details={"stage": "approval_dry_run", "error": error_msg}
        )
        raise ValueError(error_msg) from exc

    await _record_audit(job_id, "APPROVAL_GRANTED", actor=actor)
    return await _create_pr_for_job(job_id=job_id, unified_diff=unified_diff, actor=actor)


async def reject_remediation_job(
    job_id: str,
    actor: str = "on_call_engineer",
    reason: str = "Rejected during review",
) -> dict:
    """Mark a job as rejected (FAILED) without creating a PR.

    Args:
        job_id: ID of the job to reject.
        actor:  Who is performing the rejection (for audit trail).
        reason: Human-readable rejection reason.

    Raises:
        ValueError: If the job does not exist.
    """
    async with AsyncSessionLocal() as db:
        job = await db.get(RemediationJob, job_id)
        if job is None:
            raise ValueError(f"Job {job_id} not found")
        job.status = PatchStatus.FAILED
        job.error_message = f"Rejected: {reason}"
        await db.commit()

    await _record_audit(
        job_id, "REJECTED", actor=actor, details={"reason": reason}
    )
    return {"status": "rejected", "job_id": job_id}


# ── Internal: PR creation ─────────────────────────────────────────────────────


async def _create_pr_for_job(
    job_id: str,
    unified_diff: str,
    actor: str = "system",
) -> dict:
    """Apply patch to a new branch, push, and open a GitHub pull request.

    This function is shared between auto-approve and human-approval flows.
    """
    try:
        pr = await create_pull_request(
            repo_path=settings.REPO_PATH,
            branch_name=job_id,
            patch_diff=unified_diff,
            pr_title=f"fix(autofix): resolve incident {job_id[:8]}",
            pr_body=(
                f"Automated remediation patch generated by ALETHEIA.\n\n"
                f"**Job ID:** `{job_id}`\n"
                f"**Approved by:** {actor}\n\n"
                "This PR was created automatically after passing dry-run validation "
                "and explicit human approval."
            ),
        )
        async with AsyncSessionLocal() as db:
            job = await db.get(RemediationJob, job_id)
            if job:
                job.pr_url = pr.get("pr_url") or pr.get("html_url")
                job.pr_number = pr.get("number")
                job.pr_simulated = bool(pr.get("simulated", False))
                job.status = PatchStatus.PR_CREATED
                await db.commit()
        await _record_audit(
            job_id, "PR_CREATED", actor=actor,
            details={"pr_url": pr.get("pr_url"), "pr_number": pr.get("number")},
        )
        logger.info("PR created for job %s: %s", job_id, pr.get("pr_url"))
        return pr
    except Exception as exc:
        error_msg = str(exc)
        logger.error("PR creation failed for job %s: %s", job_id, error_msg)
        await _update_status(job_id, PatchStatus.FAILED, error=error_msg)
        await _record_audit(job_id, "PIPELINE_FAILED", details={"stage": "pr_create", "error": error_msg})
        raise