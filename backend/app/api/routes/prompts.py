from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.prompt import PromptTemplateCreate, PromptTemplateResponse, PromptTemplateUpdate
from app.services.prompt_service import PromptService

router = APIRouter(prefix="/api/prompts", tags=["prompts"])


def _get_or_404(service: PromptService, prompt_id: int):
    prompt = service.get(prompt_id)
    if prompt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prompt not found.")
    return prompt


@router.get("", response_model=list[PromptTemplateResponse])
def list_prompts(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return PromptService(db).list_prompts()


@router.post("", response_model=PromptTemplateResponse, status_code=status.HTTP_201_CREATED)
def create_prompt(
    payload: PromptTemplateCreate, db: Session = Depends(get_db), _: User = Depends(get_current_user)
):
    return PromptService(db).create(**payload.model_dump())


@router.get("/{prompt_id}", response_model=PromptTemplateResponse)
def get_prompt(prompt_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return _get_or_404(PromptService(db), prompt_id)


@router.put("/{prompt_id}", response_model=PromptTemplateResponse)
def update_prompt(
    prompt_id: int,
    payload: PromptTemplateUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    service = PromptService(db)
    prompt = _get_or_404(service, prompt_id)
    return service.update(prompt, **payload.model_dump(exclude_unset=True))


@router.delete("/{prompt_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_prompt(prompt_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    service = PromptService(db)
    prompt = _get_or_404(service, prompt_id)
    service.delete(prompt)


@router.post("/{prompt_id}/set-active", response_model=PromptTemplateResponse)
def set_active_prompt(prompt_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    service = PromptService(db)
    prompt = _get_or_404(service, prompt_id)
    return service.set_active(prompt)
