from sqlalchemy import select

from app.models.agent_image import AgentImage
from app.repositories.base_repository import BaseRepository


class AgentImageRepository(BaseRepository[AgentImage]):
    model = AgentImage

    def get_by_name(self, name: str) -> AgentImage | None:
        stmt = select(AgentImage).where(AgentImage.name == name)
        return self.db.scalars(stmt).first()

    def list_all(self) -> list[AgentImage]:
        stmt = select(AgentImage).order_by(AgentImage.name)
        return list(self.db.scalars(stmt).all())
