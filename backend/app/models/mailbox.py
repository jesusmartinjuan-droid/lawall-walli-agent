from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import MailboxProvider

if TYPE_CHECKING:
    from app.models.email_message import EmailMessage
    from app.models.email_thread import EmailThread


class Mailbox(Base, TimestampMixin):
    __tablename__ = "mailboxes"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email_address: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    provider: Mapped[MailboxProvider] = mapped_column(
        Enum(
            MailboxProvider,
            name="mailbox_provider",
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=MailboxProvider.NOMINALIA,
        nullable=False,
    )

    imap_host: Mapped[str] = mapped_column(String(255), nullable=False)
    imap_port: Mapped[int] = mapped_column(Integer, default=993, nullable=False)
    imap_username: Mapped[str] = mapped_column(String(255), nullable=False)
    # Encrypted at rest via app.core.encryption. Never expose in API responses.
    encrypted_imap_password: Mapped[str] = mapped_column(String(1024), nullable=False)
    imap_use_ssl: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    inbox_folder: Mapped[str] = mapped_column(String(255), default="INBOX", nullable=False)
    drafts_folder: Mapped[str] = mapped_column(String(255), default="Drafts", nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # UID (IMAP) más alto que ya existía en el buzón cuando se sincronizó por
    # primera vez. Se fija una sola vez, en el primer poll, y de ahí en
    # adelante solo se descargan correos con UID posterior — así nunca se
    # importa el histórico de un buzón recién conectado.
    initial_sync_uid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Error from the most recent poll attempt (IMAP connection/auth/etc.),
    # cleared on the next successful poll. Surfaced in the frontend so a
    # mailbox that's been failing silently is actually visible as failing —
    # last_checked_at alone updates on both success and failure.
    last_poll_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    threads: Mapped[list["EmailThread"]] = relationship(back_populates="mailbox")
    messages: Mapped[list["EmailMessage"]] = relationship(back_populates="mailbox")

    def __repr__(self) -> str:
        return f"<Mailbox id={self.id} email_address={self.email_address!r}>"
