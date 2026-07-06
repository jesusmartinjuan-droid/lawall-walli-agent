from sqlalchemy import select

from app.models.web_source import WebSource
from app.repositories.base_repository import BaseRepository


class WebSourceRepository(BaseRepository[WebSource]):
    model = WebSource

    def list_active(self) -> list[WebSource]:
        stmt = select(WebSource).where(WebSource.is_active.is_(True))
        return list(self.db.scalars(stmt).all())
