"""
AI patch generation via Google Gemini.

Reads the target source file from disk, constructs a structured prompt,
calls the Gemini API, and returns a validated `PatchResult`.

Retry policy:
    Uses `tenacity` to retry on transient API errors (503, 500, 429).
    Non-transient errors (invalid API key, 4xx) propagate immediately.

Database contract:
    This function requires a valid, open `AsyncSession`. It updates the job
    record to reflect the generated patch and sets status to GENERATED.
    The session is committed before returning. Callers must not close the
    session until after this function returns.
"""
import asyncio
import logging
import os
import uuid
from pathlib import Path

from google import genai
from google.genai import types
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from app.config import settings
from app.models.remediation import PatchStatus, RemediationJob
from app.schemas.patch import PatchResult

logger = logging.getLogger("aletheia")

_SENSITIVE_PATTERNS = {
    ".env", ".env.local", ".env.production", "id_rsa", "id_ed25519",
    "secrets.yaml", "credentials.json", "key.pem", "cert.pem",
}


def _safe_read_target_file(target_file: str, repo_root: str | None = None) -> str | None:
    """Read a target file safely within repository boundaries.

    Ensures the path does not traverse outside `settings.REPO_PATH` and
    blocks sensitive configuration and secret files from being read into
    the LLM context.
    """
    try:
        repo_root = Path(repo_root or settings.REPO_PATH).resolve()
        candidate = Path(target_file)
        if not candidate.is_absolute():
            candidate = (repo_root / candidate).resolve()
        else:
            candidate = candidate.resolve()

        # Path boundary check
        if not candidate.is_relative_to(repo_root):
            logger.warning(
                "Security: blocked attempt to read target_file outside repo: %s",
                target_file,
            )
            return None

        # Block sensitive files
        candidate_name = candidate.name.lower()
        if (
            candidate_name in _SENSITIVE_PATTERNS
            or candidate_name.startswith(".env")
            or candidate_name.endswith((".pem", ".key", ".pfx", ".p12"))
            or ".git" in candidate.parts
        ):
            logger.warning("Security: blocked attempt to read sensitive file: %s", candidate.name)
            return None

        if not candidate.is_file():
            return None

        # Size check: 500 KB limit
        if candidate.stat().st_size > 500_000:
            logger.warning("Target file %s exceeds 500KB limit, skipping file context", candidate.name)
            return None

        with open(candidate, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except Exception as exc:
        logger.warning("Could not read target file %s: %s", target_file, exc)
        return None

SYSTEM_INSTRUCTION = (
    "You are ALETHEIA, an autonomous AIOps software engineer. "
    "Analyze the provided error log and target source code to generate a precise unified diff patch "
    "that fixes the root cause.\n\n"
    "CRITICAL UNIFIED DIFF REQUIREMENTS:\n"
    "1. File header paths MUST use exact target file path with standard prefixes: `--- a/<target_file_path>` and `+++ b/<target_file_path>`.\n"
    "2. Include 3 lines of unchanged context above and below modifications.\n"
    "3. Context lines (starting with ' ') and deleted lines (starting with '-') MUST match the source code character for character.\n"
    "4. Hunk header `@@ -start,count +start,count @@` MUST have correct line numbers and count totals.\n"
    "5. Output ONLY valid JSON matching the requested schema."
)


def _demo_patch(error_log: str, target_file: str | None) -> PatchResult:
    if target_file in ("incident_demo/services/users.py", "incident-demo/services/users.py", "users.py"):
        return PatchResult(
            file_path="incident_demo/services/users.py",
            bug_description="Requests for users without a configured display name fail with AttributeError when calling upper() on None.",
            explanation="Check if display_name is not None before calling .upper(), defaulting to a fallback string or None.",
            unified_diff=(
                "--- a/incident_demo/services/users.py\n"
                "+++ b/incident_demo/services/users.py\n"
                "@@ -11,4 +11,6 @@\n"
                " def get_display_name(db: Session, user_id: int) -> str:\n"
                "     user = get_user(db, user_id)\n"
                "     # Intentionally buggy handling: calling .strip() directly on display_name without checking for None\n"
                "-    return user.display_name.strip()\n"
                "+    if user.display_name is None:\n"
                "+        return user.username\n"
                "+    return user.display_name.strip()\n"
            ),
            confidence_score=0.99,
        )
    if target_file == "transaction_service.py":
        return PatchResult(
            file_path=target_file,
            bug_description="A missing discount tier can cause a NoneType or division error during fee calculation.",
            explanation="Return the base fee when the discount tier is missing or zero before dividing.",
            unified_diff=(
                "--- a/transaction_service.py\n"
                "+++ b/transaction_service.py\n"
                "@@ -1,3 +1,5 @@\n"
                " def calculate_transaction_fee(amount, discount_tier):\n"
                "     fee = amount * 0.02\n"
                "-    return fee / discount_tier\n"
                "+    if not discount_tier:\n"
                "+        return fee\n"
                "+    return fee / discount_tier\n"
            ),
            confidence_score=0.98,
        )
    raise ValueError(
        f"No deterministic demo fixture exists for {target_file or 'the requested target'}. "
        "Set DEMO_MODE=false to use Gemini for this incident."
    )


def _is_transient_error(exc: Exception) -> bool:
    """Return True for API errors that are worth retrying."""
    msg = str(exc)
    return any(code in msg for code in ("503", "500", "429", "UNAVAILABLE", "RESOURCE_EXHAUSTED"))


@retry(
    retry=retry_if_exception(_is_transient_error),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    stop=stop_after_attempt(4),
    reraise=True,
)
def _call_gemini_sync(client: genai.Client, model_name: str, prompt: str) -> PatchResult:
    """Synchronous Gemini API call, wrapped with tenacity retry logic.

    This is intentionally synchronous because `tenacity` has no native
    async retry decorator. Called via `asyncio.to_thread` to avoid blocking
    the event loop.
    """
    logger.info("Invoking Gemini model: %s", model_name)
    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            response_schema=PatchResult,
            temperature=0.1,
        ),
    )
    return PatchResult.model_validate_json(response.text)


async def generate_patch(
    db: AsyncSession,
    error_log: str,
    target_file: str | None = None,
    job_id: str | None = None,
    repo_root: str | None = None,
) -> tuple[PatchResult, RemediationJob]:
    """Generate a patch for the given error log using Gemini AI.

    Creates or updates a `RemediationJob` record in the database, then
    calls the Gemini API to produce a `PatchResult`. On success, updates
    the job with the generated patch fields and sets status to GENERATED.

    Args:
        db:          Open SQLAlchemy async session. Caller owns the lifecycle.
        error_log:   Raw alert/error log text.
        target_file: Optional path hint for the file to patch.
        job_id:      If provided, update the existing job row; otherwise create one.

    Returns:
        Tuple of (PatchResult, RemediationJob).

    Raises:
        ValueError: If GEMINI_API_KEY is not set.
        Exception:  Any non-retried Gemini API or validation error.
    """
    if settings.DEMO_MODE:
        patch_data = _demo_patch(error_log, target_file)
        job = await db.get(RemediationJob, job_id) if job_id else None
        if job is None:
            job = RemediationJob(
                id=job_id or str(uuid.uuid4()),
                error_log=error_log,
                target_file=target_file,
                status=PatchStatus.PENDING,
            )
            db.add(job)
        job.target_file = patch_data.file_path
        job.bug_description = patch_data.bug_description
        job.explanation = patch_data.explanation
        job.unified_diff = patch_data.unified_diff
        job.confidence_score = patch_data.confidence_score
        job.status = PatchStatus.GENERATED
        await db.commit()
        await db.refresh(job)
        return patch_data, job

    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY environment variable is not set. "
            "Configure it in your .env file or deployment secrets."
        )

    model_name = os.getenv("GEMINI_MODEL", settings.GEMINI_MODEL)

    # ── Upsert the job record ─────────────────────────────────────────────────
    job: RemediationJob | None = None
    if job_id:
        job = await db.get(RemediationJob, job_id)

    if job is None:
        job = RemediationJob(
            id=job_id or str(uuid.uuid4()),
            error_log=error_log,
            target_file=target_file,
            status=PatchStatus.PENDING,
        )
        db.add(job)
    else:
        job.error_log = error_log
        if target_file:
            job.target_file = target_file

    await db.commit()
    await db.refresh(job)

    # ── Build prompt safely ───────────────────────────────────────────────────
    safe_source: str | None = None
    if target_file:
        safe_source = _safe_read_target_file(target_file, repo_root)

    prompt_parts = [
        "Analyze the following incident report and produce a precise unified diff patch.\n\n",
        f"<error_log>\n{error_log}\n</error_log>\n",
    ]
    if target_file:
        if safe_source is not None:
            prompt_parts.append(
                f"\n<target_file path=\"{target_file}\">\n{safe_source}\n</target_file>\n"
            )
        else:
            prompt_parts.append(f"\n<target_file_hint>{target_file}</target_file_hint>\n")

    prompt = "".join(prompt_parts)

    # ── Call Gemini (in thread to keep event loop free) ───────────────────────
    client = genai.Client(api_key=api_key)
    try:
        patch_data: PatchResult = await asyncio.to_thread(
            _call_gemini_sync, client, model_name, prompt
        )
    except Exception:
        job.status = PatchStatus.FAILED
        job.error_message = "Gemini API call failed after retries"
        await db.commit()
        raise

    # ── Persist patch result ──────────────────────────────────────────────────
    job.target_file = patch_data.file_path
    job.bug_description = patch_data.bug_description
    job.explanation = patch_data.explanation
    job.unified_diff = patch_data.unified_diff
    job.confidence_score = patch_data.confidence_score
    job.status = PatchStatus.GENERATED
    await db.commit()
    await db.refresh(job)

    return patch_data, job
