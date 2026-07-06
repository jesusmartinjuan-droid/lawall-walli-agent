from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utcnow
from app.models.enums import ProcessingLogStatus, ProcessingStep


class ProcessingLog(Base):
    """One row per processing attempt/step for an email, used to build the
    draft-history and processing-detail screens in the frontend."""

    __tablename__ = "processing_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    mailbox_id: Mapped[int] = mapped_column(ForeignKey("mailboxes.id", ondelete="CASCADE"), nullable=False)
    email_message_id: Mapped[int | None] = mapped_column(
        ForeignKey("email_messages.id", ondelete="CASCADE"), nullable=True
    )
    draft_id: Mapped[int | None] = mapped_column(ForeignKey("drafts.id", ondelete="SET NULL"), nullable=True)

    status: Mapped[ProcessingLogStatus] = mapped_column(
        Enum(
            ProcessingLogStatus,
            name="processing_log_status",
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=ProcessingLogStatus.PENDING,
        nullable=False,
    )
    step: Mapped[ProcessingStep] = mapped_column(
        Enum(
            ProcessingStep,
            name="processing_step",
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    def __repr__(self) -> str:
        return f"<ProcessingLog id={self.id} step={self.step} status={self.status}>"
