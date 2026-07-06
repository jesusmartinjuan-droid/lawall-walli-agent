from sqlalchemy import select

from app.models.document import Document
from app.repositories.base_repository import BaseRepository


class DocumentRepository(BaseRepository[Document]):
    model = Document

    def list_active(self) -> list[Document]:
        stmt = select(Document).where(Document.is_active.is_(True))
        return list(self.db.scalars(stmt).all())
