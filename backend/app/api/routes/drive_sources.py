from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.drive_source import DriveSourceCreate, DriveSourceResponse, DriveSourceUpdate
from app.services.drive_source_service import DriveSourceService

router = APIRouter(prefix="/api/drive-sources", tags=["drive-sources"])


def _to_response(drive_source) -> DriveSourceResponse:
    return DriveSourceResponse(
        id=drive_source.id,
        name=drive_source.name,
        drive_url=drive_source.drive_url,
        is_active=drive_source.is_active,
        openai_file_id=drive_source.openai_file_id,
        openai_file_uploaded_at=drive_source.openai_file_uploaded_at,
        size_bytes=drive_source.size_bytes,
        last_checked_at=drive_source.last_checked_at,
        last_sync_error=drive_source.last_sync_error,
        created_at=drive_source.created_at,
        updated_at=drive_source.updated_at,
    )


def _get_or_404(service: DriveSourceService, drive_source_id: int):
    drive_source = service.get(drive_source_id)
    if drive_source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Drive source not found.")
    return drive_source


@router.get("", response_model=list[DriveSourceResponse])
def list_drive_sources(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return [_to_response(d) for d in DriveSourceService(db).list_drive_sources()]


@router.post("", response_model=DriveSourceResponse, status_code=status.HTTP_201_CREATED)
def create_drive_source(
    payload: DriveSourceCreate, db: Session = Depends(get_db), _: User = Depends(get_current_user)
):
    drive_source = DriveSourceService(db).create(**payload.model_dump())
    return _to_response(drive_source)


@router.get("/{drive_source_id}", response_model=DriveSourceResponse)
def get_drive_source(
    drive_source_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)
):
    return _to_response(_get_or_404(DriveSourceService(db), drive_source_id))


@router.put("/{drive_source_id}", response_model=DriveSourceResponse)
def update_drive_source(
    drive_source_id: int,
    payload: DriveSourceUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    service = DriveSourceService(db)
    drive_source = _get_or_404(service, drive_source_id)
    updated = service.update(drive_source, **payload.model_dump(exclude_unset=True))
    return _to_response(updated)


@router.delete("/{drive_source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_drive_source(
    drive_source_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)
):
    service = DriveSourceService(db)
    drive_source = _get_or_404(service, drive_source_id)
    service.delete(drive_source)


@router.post("/{drive_source_id}/activate", response_model=DriveSourceResponse)
def activate_drive_source(
    drive_source_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)
):
    service = DriveSourceService(db)
    drive_source = _get_or_404(service, drive_source_id)
    return _to_response(service.set_active(drive_source, True))


@router.post("/{drive_source_id}/deactivate", response_model=DriveSourceResponse)
def deactivate_drive_source(
    drive_source_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)
):
    service = DriveSourceService(db)
    drive_source = _get_or_404(service, drive_source_id)
    return _to_response(service.set_active(drive_source, False))


@router.post("/{drive_source_id}/sync", response_model=DriveSourceResponse)
def sync_drive_source(
    drive_source_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)
):
    service = DriveSourceService(db)
    drive_source = _get_or_404(service, drive_source_id)
    return _to_response(service.sync(drive_source))
