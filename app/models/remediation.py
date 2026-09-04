"""
RemediationJob ORM model.

Tracks the full lifecycle of a single AI-driven remediation attempt:
from raw alert ingestion through patch generation, dry-run validation,
human approval, and final PR creation.
"""
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class PatchStatus(str, enum.Enum):
    """Ordered lifecycle states for a RemediationJob.

    Transitions:
        PENDING → GENERATING → GENERATED → DRY_RUN_PASSED
            → WAIT_FOR_APPROVAL (auto_approve=False)
            → PR_CREATED (auto_approve=True or after approval)
        Any state → FAILED (on unrecoverable error)
        PR_CREATED → APPLIED (after merge, optional)
    """

    PENDING = "PENDING"
    GENERATING = "GENERATING"
    GENERATED = "GENERATED"
    DRY_RUN_PASSED = "DRY_RUN_PASSED"
    WAIT_FOR_APPROVAL = "WAIT_FOR_APPROVAL"
    PR_CREATED = "PR_CREATED"
    APPLIED = "APPLIED"
    FAILED = "FAILED"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class RemediationJob(Base):
    """Persisted record of a single end-to-end remediation pipeline run."""

    __tablename__ = "remediation_jobs"

    # Primary key — UUID string so it's safe to leak in API responses
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )

    # Input
    error_log: Mapped[str] = mapped_column(Text, nullable=False)
    target_file: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # AI output
    bug_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    unified_diff: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Lifecycle
    status: Mapped[PatchStatus] = mapped_column(
        Enum(PatchStatus), default=PatchStatus.PENDING, nullable=False, index=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps — stored as UTC, use timezone.utc throughout
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )
