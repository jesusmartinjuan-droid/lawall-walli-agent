from sqlalchemy import select

from app.models.prompt import PromptTemplate
from app.repositories.base_repository import BaseRepository


class PromptRepository(BaseRepository[PromptTemplate]):
    model = PromptTemplate

    def get_default(self) -> PromptTemplate | None:
        stmt = select(PromptTemplate).where(
            PromptTemplate.is_default.is_(True), PromptTemplate.is_active.is_(True)
        )
        return self.db.scalars(stmt).first()

    def clear_default_flag(self) -> None:
        stmt = select(PromptTemplate).where(PromptTemplate.is_default.is_(True))
        for prompt in self.db.scalars(stmt).all():
            prompt.is_default = False
        self.db.flush()
