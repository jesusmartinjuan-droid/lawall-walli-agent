from sqlalchemy import select

from app.models.mailbox import Mailbox
from app.repositories.base_repository import BaseRepository


class MailboxRepository(BaseRepository[Mailbox]):
    model = Mailbox

    def list_active(self) -> list[Mailbox]:
        stmt = select(Mailbox).where(Mailbox.is_active.is_(True))
        return list(self.db.scalars(stmt).all())

    def get_by_email_address(self, email_address: str) -> Mailbox | None:
        stmt = select(Mailbox).where(Mailbox.email_address == email_address)
        return self.db.scalars(stmt).first()
