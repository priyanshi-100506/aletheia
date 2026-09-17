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
import difflib
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
from app.schemas.patch import PatchProposal, PatchResult

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


def construct_deterministic_patch(
    source_content: str,
    target_file: str,
    original_code: str,
    replacement_code: str,
) -> str:
    """Construct a deterministic unified diff by replacing original_code with replacement_code in source_content.

    Validation rules:
    1. original_code must exist in source_content.
    2. original_code must match unambiguously (exact 1 occurrence).
    3. Returns unified diff formatted with standard a/ and b/ headers and trailing newline.
    """
    if not original_code:
        raise ValueError("Original code snippet proposed by model cannot be empty")

    norm_source = source_content.replace("\r\n", "\n")
    norm_orig = original_code.replace("\r\n", "\n")
    norm_repl = replacement_code.replace("\r\n", "\n")

    count = norm_source.count(norm_orig)
    if count == 0:
        raise ValueError(
            f"Original code region proposed for '{target_file}' was not found in the target source file."
        )
    if count > 1:
        raise ValueError(
            f"Original code region proposed for '{target_file}' is ambiguous (matches {count} times)."
        )

    modified_content = norm_source.replace(norm_orig, norm_repl, 1)

    clean_target = target_file.lstrip("./")
    from_file = f"a/{clean_target}"
    to_file = f"b/{clean_target}"

    source_lines = norm_source.splitlines(keepends=True)
    modified_lines = modified_content.splitlines(keepends=True)

    if source_lines and not source_lines[-1].endswith("\n"):
        source_lines[-1] += "\n"
    if modified_lines and not modified_lines[-1].endswith("\n"):
        modified_lines[-1] += "\n"

    diff_lines = list(
        difflib.unified_diff(
            source_lines,
            modified_lines,
            fromfile=from_file,
            tofile=to_file,
            n=3,
        )
    )

    if not diff_lines:
        raise ValueError(f"No changes produced for '{target_file}' (original and replacement are identical).")

    unified_diff = "".join(diff_lines)
    if not unified_diff.endswith("\n"):
        unified_diff += "\n"

    return unified_diff


SYSTEM_INSTRUCTION = (
    "You are ALETHEIA, an autonomous AIOps software engineer. "
    "Analyze the provided error log and target source code to identify the root cause and propose a precise code fix.\n\n"
    "CRITICAL PROPOSAL REQUIREMENTS:\n"
    "1. `file_path`: MUST be the exact target file path provided in context.\n"
    "2. `original_code`: MUST be the exact snippet of original code from the target file that needs to be replaced. Include enough surrounding context if needed to ensure it matches uniquely in the file.\n"
    "3. `replacement_code`: MUST be the exact new code snippet to replace `original_code`.\n"
    "4. Do NOT output unified diffs or calculate line numbers manually.\n"
    "5. Output ONLY valid JSON matching the requested schema."
)


def _demo_patch(error_log: str, target_file: str | None, safe_source: str | None = None) -> PatchResult:
    if target_file in ("incident_demo/services/users.py", "incident-demo/services/users.py", "users.py"):
        orig = "    return user.display_name.strip()\n"
        repl = "    if user.display_name is None:\n        return user.username\n    return user.display_name.strip()\n"
        if safe_source:
            diff = construct_deterministic_patch(safe_source, target_file, orig, repl)
        else:
            diff = (
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
            )
        return PatchResult(
            file_path="incident_demo/services/users.py",
            bug_description="Requests for users without a configured display name fail with AttributeError when calling upper() on None.",
            explanation="Check if display_name is not None before calling .upper(), defaulting to a fallback string or None.",
            unified_diff=diff,
            confidence_score=0.99,
            original_code=orig,
            replacement_code=repl,
        )
    if target_file == "transaction_service.py":
        orig = "    return fee / discount_tier\n"
        repl = "    if not discount_tier:\n        return fee\n    return fee / discount_tier\n"
        if safe_source:
            diff = construct_deterministic_patch(safe_source, target_file, orig, repl)
        else:
            diff = (
                "--- a/transaction_service.py\n"
                "+++ b/transaction_service.py\n"
                "@@ -1,3 +1,5 @@\n"
                " def calculate_transaction_fee(amount, discount_tier):\n"
                "     fee = amount * 0.02\n"
                "-    return fee / discount_tier\n"
                "+    if not discount_tier:\n"
                "+        return fee\n"
                "+    return fee / discount_tier\n"
            )
        return PatchResult(
            file_path=target_file,
            bug_description="A missing discount tier can cause a NoneType or division error during fee calculation.",
            explanation="Return the base fee when the discount tier is missing or zero before dividing.",
            unified_diff=diff,
            confidence_score=0.98,
            original_code=orig,
            replacement_code=repl,
        )
    raise ValueError(
        f"No deterministic demo fixture exists for {target_file or 'the requested target'}. "
        "Set DEMO_MODE=false to use Gemini for this incident."
    )


def _is_transient_error(exc: Exception) -> bool:
    """Return True for API errors that are worth retrying."""
    msg = str(exc)
    return any(code in msg for code in ("503", "500", "429", "UNAVAILABLE", "RESOURCE_EXHAUSTED", "getaddrinfo", "11002", "ConnectError", "TimeoutError", "socket"))



@retry(
    retry=retry_if_exception(_is_transient_error),
    wait=wait_exponential(multiplier=2, min=2, max=60),
    stop=stop_after_attempt(8),
    reraise=True,
)

def _call_gemini_sync(client: genai.Client, model_name: str, prompt: str) -> PatchProposal:
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
            response_schema=PatchProposal,
            temperature=0.1,
        ),
    )
    return PatchProposal.model_validate_json(response.text)


async def generate_patch(
    db: AsyncSession,
    error_log: str,
    target_file: str | None = None,
    job_id: str | None = None,
    repo_root: str | None = None,
    target_test: str | None = None,
) -> tuple[PatchResult, RemediationJob]:
    """Generate a patch for the given error log using Gemini AI."""
    if not target_file:
        raise ValueError("target_file is required to generate a patch")

    safe_source = _safe_read_target_file(target_file, repo_root)

    if settings.DEMO_MODE:
        patch_data = _demo_patch(error_log, target_file, safe_source=safe_source)
        job = await db.get(RemediationJob, job_id) if job_id else None
        if job is None:
            job = RemediationJob(
                id=job_id or str(uuid.uuid4()),
                error_log=error_log,
                target_file=target_file,
                target_test=target_test,
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

    if safe_source is None:
        raise ValueError(
            f"Target file '{target_file}' could not be read from repository checkout"
        )

    api_key = os.getenv("GEMINI_API_KEY", "") or settings.GEMINI_API_KEY
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
            target_test=target_test,
            status=PatchStatus.PENDING,
        )
        db.add(job)
    else:
        job.error_log = error_log
        if target_file:
            job.target_file = target_file
        if target_test:
            job.target_test = target_test

    await db.commit()
    await db.refresh(job)

    # Fetch target_test from job if not passed directly
    if not target_test and job.target_test:
        target_test = job.target_test

    # ── Build prompt ──────────────────────────────────────────────────────────
    prompt_parts = [
        "Analyze the following incident report and target source file. ",
        "Identify the root cause and propose a code change.\n\n",
        f"<error_log>\n{error_log}\n</error_log>\n\n",
        f'<target_file path="{target_file}">\n{safe_source}\n</target_file>\n',
    ]

    if target_test:
        test_file_path = target_test.split("::")[0]
        safe_test_source = _safe_read_target_file(test_file_path, repo_root)
        if safe_test_source:
            prompt_parts.append(
                f'\n<target_test_file path="{test_file_path}">\n{safe_test_source}\n</target_test_file>\n'
            )

    prompt = "".join(prompt_parts)


    # ── Call Gemini ───────────────────────────────────────────────────────────
    client = genai.Client(api_key=api_key)
    try:
        proposal: PatchProposal = await asyncio.to_thread(
            _call_gemini_sync, client, model_name, prompt
        )
    except Exception as exc:
        job.status = PatchStatus.FAILED
        job.error_message = f"Gemini API call failed: {exc}"
        await db.commit()
        raise

    # ── Validate proposed target path ─────────────────────────────────────────
    clean_target = target_file.lstrip("./")
    clean_prop_path = proposal.file_path.lstrip("./")
    if clean_prop_path != clean_target and not clean_target.endswith(clean_prop_path):
        error_msg = f"Proposal file path '{proposal.file_path}' does not match target file '{target_file}'"
        job.status = PatchStatus.FAILED
        job.error_message = error_msg
        await db.commit()
        raise ValueError(error_msg)

    # Ensure the proposal includes required code snippets
    if not proposal.original_code or not proposal.replacement_code:
        error_msg = "PatchProposal missing original_code or replacement_code; cannot construct deterministic diff."
        job.status = PatchStatus.FAILED
        job.error_message = error_msg
        await db.commit()
        raise ValueError(error_msg)

    # ── Deterministically construct unified diff ──────────────────────────────
    try:
        unified_diff = construct_deterministic_patch(
            source_content=safe_source,
            target_file=target_file,
            original_code=proposal.original_code,
            replacement_code=proposal.replacement_code,
        )
    except Exception as exc:
        error_msg = f"Patch construction failed: {exc}"
        job.status = PatchStatus.FAILED
        job.error_message = error_msg
        await db.commit()
        raise ValueError(error_msg) from exc

    patch_data = PatchResult(
        file_path=target_file,
        bug_description=proposal.bug_description,
        explanation=proposal.explanation,
        unified_diff=unified_diff,
        confidence_score=proposal.confidence_score,
        original_code=proposal.original_code,
        replacement_code=proposal.replacement_code,
    )

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

