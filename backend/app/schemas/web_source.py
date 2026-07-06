from datetime import datetime

from pydantic import BaseModel


class WebSourceBase(BaseModel):
    name: str
    root_url: str
    max_pages: int = 20


class WebSourceCreate(WebSourceBase):
    is_active: bool = True


class WebSourceUpdate(BaseModel):
    name: str | None = None
    root_url: str | None = None
    max_pages: int | None = None
    is_active: bool | None = None


class WebSourceResponse(WebSourceBase):
    id: int
    is_active: bool
    pages_crawled: int | None
    text_length: int = 0
    last_fetched_at: datetime | None
    last_fetch_error: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
