from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.web_source import WebSourceCreate, WebSourceResponse, WebSourceUpdate
from app.services.web_source_service import WebSourceService

router = APIRouter(prefix="/api/web-sources", tags=["web-sources"])


def _to_response(web_source) -> WebSourceResponse:
    return WebSourceResponse(
        id=web_source.id,
        name=web_source.name,
        root_url=web_source.root_url,
        max_pages=web_source.max_pages,
        is_active=web_source.is_active,
        pages_crawled=web_source.pages_crawled,
        text_length=len(web_source.extracted_text or ""),
        last_fetched_at=web_source.last_fetched_at,
        last_fetch_error=web_source.last_fetch_error,
        created_at=web_source.created_at,
        updated_at=web_source.updated_at,
    )


def _get_or_404(service: WebSourceService, web_source_id: int):
    web_source = service.get(web_source_id)
    if web_source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Web source not found.")
    return web_source


@router.get("", response_model=list[WebSourceResponse])
def list_web_sources(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return [_to_response(w) for w in WebSourceService(db).list_web_sources()]


@router.post("", response_model=WebSourceResponse, status_code=status.HTTP_201_CREATED)
def create_web_source(
    payload: WebSourceCreate, db: Session = Depends(get_db), _: User = Depends(get_current_user)
):
    web_source = WebSourceService(db).create(**payload.model_dump())
    return _to_response(web_source)


@router.get("/{web_source_id}", response_model=WebSourceResponse)
def get_web_source(web_source_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return _to_response(_get_or_404(WebSourceService(db), web_source_id))


@router.put("/{web_source_id}", response_model=WebSourceResponse)
def update_web_source(
    web_source_id: int,
    payload: WebSourceUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    service = WebSourceService(db)
    web_source = _get_or_404(service, web_source_id)
    updated = service.update(web_source, **payload.model_dump(exclude_unset=True))
    return _to_response(updated)


@router.delete("/{web_source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_web_source(
    web_source_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)
):
    service = WebSourceService(db)
    web_source = _get_or_404(service, web_source_id)
    service.delete(web_source)


@router.post("/{web_source_id}/activate", response_model=WebSourceResponse)
def activate_web_source(
    web_source_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)
):
    service = WebSourceService(db)
    web_source = _get_or_404(service, web_source_id)
    return _to_response(service.set_active(web_source, True))


@router.post("/{web_source_id}/deactivate", response_model=WebSourceResponse)
def deactivate_web_source(
    web_source_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)
):
    service = WebSourceService(db)
    web_source = _get_or_404(service, web_source_id)
    return _to_response(service.set_active(web_source, False))


@router.post("/{web_source_id}/refresh", response_model=WebSourceResponse)
def refresh_web_source(
    web_source_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)
):
    service = WebSourceService(db)
    web_source = _get_or_404(service, web_source_id)
    return _to_response(service.refresh(web_source))
