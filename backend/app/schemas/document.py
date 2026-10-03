from datetime import datetime

from pydantic import BaseModel


class DocumentResponse(BaseModel):
    id: int
    filename: str
    original_filename: str
    content_type: str
    is_active: bool
    size_bytes: int
    openai_file_id: str | None
    openai_file_uploaded_at: datetime | None
    openai_upload_error: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
