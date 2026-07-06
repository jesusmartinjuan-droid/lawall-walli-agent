from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import EmailThreadStatus

if TYPE_CHECKING:
    from app.models.email_message import EmailMessage
    from app.models.mailbox import Mailbox


class EmailThread(Base, TimestampMixin):
    __tablename__ = "email_threads"
    __table_args__ = (
        UniqueConstraint("mailbox_id", "external_thread_id", name="uq_thread_mailbox_external_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    mailbox_id: Mapped[int] = mapped_column(ForeignKey("mailboxes.id", ondelete="CASCADE"), nullable=False)
    external_thread_id: Mapped[str] = mapped_column(String(998), nullable=False)
    subject: Mapped[str] = mapped_column(String(998), nullable=False)
    customer_email: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[EmailThreadStatus] = mapped_column(
        Enum(
            EmailThreadStatus,
            name="email_thread_status",
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=EmailThreadStatus.OPEN,
        nullable=False,
    )

    mailbox: Mapped["Mailbox"] = relationship(back_populates="threads")
    messages: Mapped[list["EmailMessage"]] = relationship(back_populates="thread")

    def __repr__(self) -> str:
        return f"<EmailThread id={self.id} subject={self.subject!r}>"
