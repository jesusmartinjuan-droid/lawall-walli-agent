from sqlalchemy.orm import Session

from app.models.draft import Draft
from app.repositories.draft_repository import DraftRepository


class DraftService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = DraftRepository(db)

    def list_drafts(self, limit: int = 100, offset: int = 0) -> list[Draft]:
        return self.repo.list(limit=limit, offset=offset)

    def get(self, draft_id: int) -> Draft | None:
        return self.repo.get(draft_id)
