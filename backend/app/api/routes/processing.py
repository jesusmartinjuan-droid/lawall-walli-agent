from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.processing import (
    ProcessingDetail,
    ProcessingListItem,
    SimulateDraftRequest,
    SimulateDraftResponse,
)
from app.services.llm_service import LLMProviderError
from app.services.processing_service import ProcessingService

router = APIRouter(prefix="/api/processing", tags=["processing"])


@router.post("/simulate", response_model=SimulateDraftResponse)
def simulate_draft(
    payload: SimulateDraftRequest, db: Session = Depends(get_db), _: User = Depends(get_current_user)
):
    try:
        return ProcessingService(db).simulate_draft(payload.email_body)
    except LLMProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"No se pudo generar el borrador de prueba: {exc}",
        ) from exc


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
