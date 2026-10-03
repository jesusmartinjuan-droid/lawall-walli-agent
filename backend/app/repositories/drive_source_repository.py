from sqlalchemy import select

from app.models.drive_source import DriveSource
from app.repositories.base_repository import BaseRepository


class DriveSourceRepository(BaseRepository[DriveSource]):
    model = DriveSource

    def list_active(self) -> list[DriveSource]:
        stmt = select(DriveSource).where(DriveSource.is_active.is_(True))
        return list(self.db.scalars(stmt).all())
