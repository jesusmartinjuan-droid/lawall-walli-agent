from datetime import datetime

from pydantic import BaseModel


class DriveSourceBase(BaseModel):
    name: str
    drive_url: str


class DriveSourceCreate(DriveSourceBase):
    is_active: bool = True


class DriveSourceUpdate(BaseModel):
    name: str | None = None
    drive_url: str | None = None
    is_active: bool | None = None


class DriveSourceResponse(DriveSourceBase):
    id: int
    is_active: bool
    openai_file_id: str | None
    openai_file_uploaded_at: datetime | None
    size_bytes: int | None
    last_checked_at: datetime | None
    last_sync_error: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
