from datetime import datetime

from pydantic import BaseModel


class AgentImageResponse(BaseModel):
    id: int
    name: str
    description: str
    original_filename: str
    content_type: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
