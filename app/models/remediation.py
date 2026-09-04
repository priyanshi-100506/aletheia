import enum
import uuid
from datetime import datetime
from sqlalchemy import String, Text, Float, Enum, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.db.database import Base

class PatchStatus(str, enum.Enum):
    PENDING = "PENDING"
    GENERATING = "GENERATING"
    GENERATED = "GENERATED"
    DRY_RUN_PASSED = "DRY_RUN_PASSED"
    PR_CREATED = "PR_CREATED"
    APPLIED = "APPLIED"
    FAILED = "FAILED"

class RemediationJob(Base):
    __tablename__ = "remediation_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    error_log: Mapped[str] = mapped_column(Text, nullable=False)
    target_file: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bug_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    unified_diff: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[PatchStatus] = mapped_column(Enum(PatchStatus), default=PatchStatus.PENDING, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
