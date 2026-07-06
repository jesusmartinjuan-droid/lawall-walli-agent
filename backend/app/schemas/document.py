from datetime import datetime

from pydantic import BaseModel


class DocumentResponse(BaseModel):
    id: int
    filename: str
    original_filename: str
    content_type: str
    is_active: bool
    text_length: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
