from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.processing import ProcessingDetail, ProcessingListItem
from app.services.processing_service import ProcessingService

router = APIRouter(prefix="/api/processing", tags=["processing"])


@router.get("", response_model=list[ProcessingListItem])
def list_processing(
    limit: int = 100, offset: int = 0, db: Session = Depends(get_db), _: User = Depends(get_current_user)
):
    return ProcessingService(db).list_processing(limit=limit, offset=offset)


@router.get("/{email_message_id}", response_model=ProcessingDetail)
def get_processing_detail(
    email_message_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)
):
    detail = ProcessingService(db).get_processing_detail(email_message_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Processing record not found.")
    return detail
