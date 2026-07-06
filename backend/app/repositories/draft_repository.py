from sqlalchemy import select

from app.models.draft import Draft
from app.repositories.base_repository import BaseRepository


class DraftRepository(BaseRepository[Draft]):
    model = Draft

    def get_by_email_message_id(self, email_message_id: int) -> Draft | None:
        stmt = select(Draft).where(Draft.email_message_id == email_message_id).order_by(Draft.id.desc())
        return self.db.scalars(stmt).first()
