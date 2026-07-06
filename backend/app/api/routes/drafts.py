from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.draft import DraftListItem, DraftResponse
from app.services.draft_service import DraftService

router = APIRouter(prefix="/api/drafts", tags=["drafts"])


@router.get("", response_model=list[DraftListItem])
def list_drafts(
    limit: int = 100, offset: int = 0, db: Session = Depends(get_db), _: User = Depends(get_current_user)
):
    return DraftService(db).list_drafts(limit=limit, offset=offset)


@router.get("/{draft_id}", response_model=DraftResponse)
def get_draft(draft_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    draft = DraftService(db).get(draft_id)
    if draft is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found.")
    return draft
