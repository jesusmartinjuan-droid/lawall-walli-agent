from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.draft import Draft
    from app.models.email_thread import EmailThread
    from app.models.mailbox import Mailbox


class EmailMessage(Base):
    """A single email fetched from a mailbox.

    Duplicate protection relies on the (mailbox_id, imap_uid) pair, which is
    stable per mailbox/folder in IMAP, plus a secondary unique constraint on
    (mailbox_id, external_message_id) since the RFC822 Message-ID is globally
    unique when present.
    """

    __tablename__ = "email_messages"
    __table_args__ = (
        UniqueConstraint("mailbox_id", "imap_uid", name="uq_email_mailbox_imap_uid"),
        UniqueConstraint("mailbox_id", "external_message_id", name="uq_email_mailbox_external_message_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    mailbox_id: Mapped[int] = mapped_column(ForeignKey("mailboxes.id", ondelete="CASCADE"), nullable=False)
    thread_id: Mapped[int | None] = mapped_column(
        ForeignKey("email_threads.id", ondelete="SET NULL"), nullable=True
    )

    external_message_id: Mapped[str] = mapped_column(String(998), nullable=False)
    imap_uid: Mapped[int] = mapped_column(Integer, nullable=False)

    sender: Mapped[str] = mapped_column(String(255), nullable=False)
    recipients: Mapped[str] = mapped_column(String(1000), nullable=False)
    subject: Mapped[str] = mapped_column(String(998), nullable=False, default="")
    body_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_html: Mapped[str | None] = mapped_column(Text, nullable=True)

    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    mailbox: Mapped["Mailbox"] = relationship(back_populates="messages")
    thread: Mapped["EmailThread | None"] = relationship(back_populates="messages")
    drafts: Mapped[list["Draft"]] = relationship(back_populates="email_message")

    def __repr__(self) -> str:
        return f"<EmailMessage id={self.id} subject={self.subject!r}>"
