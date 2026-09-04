from pydantic import BaseModel, Field

class PatchResult(BaseModel):
    file_path: str = Field(description="The relative file path being patched.")
    explanation: str = Field(description="Brief explanation of why the error occurred and how the fix works.")
    bug_description: str = Field(description="Summary of the root cause/vulnerability identified.")
    unified_diff: str = Field(description="A valid git/unified diff format patch applying the fix.")
    confidence_score: float = Field(description="Confidence score between 0.0 and 1.0.")
