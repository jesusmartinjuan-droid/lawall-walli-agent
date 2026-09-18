from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.agent_image import AgentImageResponse
from app.services.agent_image_service import (
    AgentImageService,
    DuplicateAgentImageNameError,
    UnsupportedAgentImageError,
)

router = APIRouter(prefix="/api/agent-images", tags=["agent-images"])


class AgentImageUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


def _to_response(image) -> AgentImageResponse:
    return AgentImageResponse(
        id=image.id,
        name=image.name,
        description=image.description,
        original_filename=image.original_filename,
        content_type=image.content_type,
        created_at=image.created_at,
        updated_at=image.updated_at,
    )


@router.get("", response_model=list[AgentImageResponse])
def list_agent_images(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return [_to_response(image) for image in AgentImageService(db).list_all()]


@router.post("", response_model=AgentImageResponse, status_code=status.HTTP_201_CREATED)
async def create_agent_image(
    name: str = Form(...),
    description: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    service = AgentImageService(db)
    file_bytes = await file.read()
    try:
        image = service.create(
            name=name,
            description=description,
            original_filename=file.filename or "image",
            file_bytes=file_bytes,
        )
    except UnsupportedAgentImageError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except DuplicateAgentImageNameError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _to_response(image)


@router.patch("/{image_id}", response_model=AgentImageResponse)
def update_agent_image(
    image_id: int,
    payload: AgentImageUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    try:
        image = AgentImageService(db).update_metadata(
            image_id, name=payload.name, description=payload.description
        )
    except DuplicateAgentImageNameError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if image is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found.")
    return _to_response(image)


@router.get("/{image_id}/preview")
def preview_agent_image(image_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    service = AgentImageService(db)
    image = service.get(image_id)
    if image is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found.")
    return Response(content=service.read_bytes(image), media_type=image.content_type)


@router.delete("/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_agent_image(image_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    deleted = AgentImageService(db).delete(image_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found.")
