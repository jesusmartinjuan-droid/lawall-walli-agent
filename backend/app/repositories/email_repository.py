from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.email_message import EmailMessage
from app.models.email_thread import EmailThread
from app.repositories.base_repository import BaseRepository


class EmailThreadRepository(BaseRepository[EmailThread]):
    model = EmailThread

    def get_by_external_id(self, mailbox_id: int, external_thread_id: str) -> EmailThread | None:
        stmt = select(EmailThread).where(
            EmailThread.mailbox_id == mailbox_id,
            EmailThread.external_thread_id == external_thread_id,
        )
        return self.db.scalars(stmt).first()


class EmailMessageRepository(BaseRepository[EmailMessage]):
    model = EmailMessage

    def __init__(self, db: Session):
        super().__init__(db)

    def exists_by_uid(self, mailbox_id: int, imap_uid: int) -> bool:
        stmt = select(EmailMessage.id).where(
            EmailMessage.mailbox_id == mailbox_id, EmailMessage.imap_uid == imap_uid
        )
        return self.db.scalars(stmt).first() is not None

    def exists_by_external_message_id(self, mailbox_id: int, external_message_id: str) -> bool:
        stmt = select(EmailMessage.id).where(
            EmailMessage.mailbox_id == mailbox_id,
            EmailMessage.external_message_id == external_message_id,
        )
        return self.db.scalars(stmt).first() is not None

    def list_thread_messages(
        self, thread_id: int, exclude_message_id: int | None = None
    ) -> list[EmailMessage]:
        stmt = (
            select(EmailMessage)
            .where(EmailMessage.thread_id == thread_id)
            .order_by(EmailMessage.received_at.asc())
        )
        messages = list(self.db.scalars(stmt).all())
        if exclude_message_id is not None:
            messages = [m for m in messages if m.id != exclude_message_id]
        return messages
