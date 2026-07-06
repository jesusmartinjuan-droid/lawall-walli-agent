from datetime import datetime

from pydantic import BaseModel


class PromptTemplateBase(BaseModel):
    name: str
    description: str | None = None
    content: str
    is_active: bool = True


class PromptTemplateCreate(PromptTemplateBase):
    pass


class PromptTemplateUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    content: str | None = None
    is_active: bool | None = None


class PromptTemplateResponse(PromptTemplateBase):
    id: int
    is_default: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
