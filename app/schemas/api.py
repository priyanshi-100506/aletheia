from pydantic import BaseModel, Field
from app.schemas.patch import PatchResult

class ErrorLogRequest(BaseModel):
    error_log: str = Field(..., min_length=1, max_length=100_000, description="Raw error log or stack trace.")
    target_file: str | None = Field(None, max_length=255, description="Optional path to target file.")

class RemediationResponse(BaseModel):
    status: str = "success"
    job_id: str
    patch: PatchResult

class ApplyPatchRequest(BaseModel):
    job_id: str | None = Field(None, description="Remediation job ID to update status.")
    unified_diff: str = Field(..., min_length=1, max_length=500_000, description="Unified diff content to apply.")
    repo_root: str = Field(".", max_length=255, description="Root path of repository.")
    dry_run: bool = Field(False, description="If True, performs validation only.")

class ApplyPatchResponse(BaseModel):
    status: str
    job_id: str | None = None
    detail: str
