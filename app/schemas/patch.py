from pydantic import BaseModel, Field


class PatchProposal(BaseModel):
    file_path: str = Field(max_length=512, description="The relative file path being patched.")
    explanation: str = Field(max_length=20_000, description="Brief explanation of why the error occurred and how the fix works.")
    bug_description: str = Field(max_length=20_000, description="Summary of the root cause/vulnerability identified.")
    original_code: str = Field(description="The exact snippet of original code to replace from the source file.")
    replacement_code: str = Field(description="The exact replacement code snippet.")
    confidence_score: float = Field(ge=0.0, le=1.0, description="Confidence score between 0.0 and 1.0.")


class PatchResult(BaseModel):
    file_path: str = Field(max_length=512, description="The relative file path being patched.")
    explanation: str = Field(max_length=20_000, description="Brief explanation of why the error occurred and how the fix works.")
    bug_description: str = Field(max_length=20_000, description="Summary of the root cause/vulnerability identified.")
    unified_diff: str = Field(max_length=500_000, description="A valid git/unified diff format patch applying the fix.")
    confidence_score: float = Field(ge=0.0, le=1.0, description="Confidence score between 0.0 and 1.0.")
    original_code: str | None = Field(default=None, description="The exact original code region replaced.")
    replacement_code: str | None = Field(default=None, description="The replacement code region.")

