import os
import uuid
import logging
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from google import genai
from google.genai import types
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception, stop_after_delay

from app.schemas.patch import PatchResult
from app.models.remediation import RemediationJob, PatchStatus

logger = logging.getLogger("aletheia")

SYSTEM_INSTRUCTION = """
You are ALETHEIA, an autonomous AIOps software engineer. 
Analyze error logs and generate precise unified diff patches to fix the root cause.
Output strictly according to the requested response schema.
"""

def is_transient_error(exception: Exception) -> bool:
    """Retry on 503, 500, or rate limits."""
    err_str = str(exception)
    return "503" in err_str or "UNAVAILABLE" in err_str or "429" in err_str or "500" in err_str

@retry(
    retry=retry_if_exception(is_transient_error),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    stop=stop_after_attempt(4),
    reraise=True
)
def _call_gemini_with_retry(client: genai.Client, prompt: str) -> PatchResult:
    logger.info("[GEMINI API] Invoking gemini-3.6-flash model...")
    model_name = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            response_schema=PatchResult,
            temperature=0.1
        )
    )
    return PatchResult.model_validate_json(response.text)

async def generate_patch(
    db: AsyncSession, 
    error_log: str, 
    target_file: str | None = None,
    job_id: str | None = None
) -> tuple[PatchResult, RemediationJob]:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable is not set.")

    db_active = True
    try:
        existing = None
        if job_id:
            existing = await db.get(RemediationJob, job_id)
        
        if existing:
            job = existing
            job.error_log = error_log
            if target_file:
                job.target_file = target_file
        else:
            job = RemediationJob(
                id=job_id or str(uuid.uuid4()),
                error_log=error_log,
                target_file=target_file,
                status=PatchStatus.PENDING
            )
            db.add(job)
            
        await db.commit()
        await db.refresh(job)
    except Exception as db_err:
        db_active = False
        await db.rollback()
        logger.warning(f"[DB SKIPPED] Running in standalone mode: {db_err}")

    try:
        client = genai.Client(api_key=api_key)
        prompt = f"Error Log:\n{error_log}\n"
        if target_file:
            prompt += f"\nTarget File Path: {target_file}\n"
            if os.path.exists(target_file):
                try:
                    with open(target_file, "r", encoding="utf-8") as f:
                        file_code = f.read()
                    prompt += f"\nExisting Target File Content:\n```python\n{file_code}\n```\n"
                except Exception as file_err:
                    logger.warning(f"Could not read target file {target_file}: {file_err}")

        patch_data = await asyncio.to_thread(_call_gemini_with_retry, client, prompt)

        job.target_file = patch_data.file_path
        job.bug_description = patch_data.bug_description
        job.explanation = patch_data.explanation
        job.unified_diff = patch_data.unified_diff
        job.confidence_score = patch_data.confidence_score
        job.status = PatchStatus.GENERATED
        
        if db_active:
            try:
                await db.commit()
                await db.refresh(job)
            except Exception as db_err:
                logger.warning(f"[DB SKIPPED] Failed updating job status: {db_err}")

        return patch_data, job

    except Exception as e:
        if db_active:
            try:
                job.status = PatchStatus.FAILED
                job.error_message = str(e)
                await db.commit()
            except Exception:
                pass
        raise e
