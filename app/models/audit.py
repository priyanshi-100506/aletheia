"""
AuditLog ORM model.

Append-only table for security and operational events. Never delete rows.
Every significant action in ALETHEIA (webhook ingest, patch generation,
approval, rejection, PR creation) writes an entry here.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AuditLog(Base):
    """Immutable audit trail entry."""

    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )

    # The RemediationJob this event belongs to (nullable for system-level events)
    job_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)

    # Structured event type — use SCREAMING_SNAKE_CASE constants:
    #   WEBHOOK_INGESTED, PIPELINE_STARTED, PATCH_GENERATED, DRY_RUN_PASSED,
    #   AWAITING_APPROVAL, APPROVAL_GRANTED, REJECTED, PR_CREATED,
    #   PIPELINE_FAILED, RATE_LIMITED, SIGNATURE_INVALID
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # Who triggered this event: "system" | "on_call_engineer" | username
    actor: Mapped[str] = mapped_column(String(128), nullable=False, default="system")

    # Arbitrary structured data (confidence score, PR URL, error message, etc.)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
