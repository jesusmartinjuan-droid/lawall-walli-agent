"""Generic CRUD repository shared by all entity-specific repositories.

Keeping this thin and generic avoids duplicating basic query boilerplate;
entity-specific query logic still lives in the dedicated repository classes.
"""

from typing import Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    model: type[ModelType]

    def __init__(self, db: Session):
        self.db = db

    def get(self, id_: int) -> ModelType | None:
        return self.db.get(self.model, id_)

    def list(self, limit: int = 100, offset: int = 0) -> list[ModelType]:
        stmt = select(self.model).order_by(self.model.id.desc()).limit(limit).offset(offset)
        return list(self.db.scalars(stmt).all())

    def add(self, entity: ModelType) -> ModelType:
        self.db.add(entity)
        self.db.flush()
        return entity

    def delete(self, entity: ModelType) -> None:
        self.db.delete(entity)
        self.db.flush()

    def commit(self) -> None:
        self.db.commit()

    def refresh(self, entity: ModelType) -> None:
        self.db.refresh(entity)
