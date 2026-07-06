from datetime import datetime

from pydantic import BaseModel

from app.models.enums import DraftStatus


class DraftResponse(BaseModel):
    id: int
    mailbox_id: int
    email_message_id: int
    prompt_template_id: int | None
    generated_body: str
    llm_provider: str
    llm_model: str
    input_tokens: int | None
    output_tokens: int | None
    estimated_cost: float | None
    status: DraftStatus
    created_in_mailbox: bool
    mailbox_draft_id: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DraftListItem(BaseModel):
    id: int
    mailbox_id: int
    status: DraftStatus
    created_in_mailbox: bool
    created_at: datetime

    model_config = {"from_attributes": True}
