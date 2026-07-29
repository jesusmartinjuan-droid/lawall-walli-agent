from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import ProcessingLogStatus, ProcessingStatus, ProcessingStep


class ProcessingLogItem(BaseModel):
    id: int
    status: ProcessingLogStatus
    step: ProcessingStep
    error_message: str | None
    retry_count: int
    started_at: datetime
    finished_at: datetime | None

    model_config = {"from_attributes": True}


class ProcessingListItem(BaseModel):
    """Row for the draft-history / processing-list screen: one email + its
    latest known status, mailbox and generated draft (if any)."""

    email_message_id: int
    mailbox_id: int
    mailbox_name: str
    subject: str
    sender: str
    received_at: datetime
    status: ProcessingStatus
    draft_id: int | None
    error_message: str | None


class ProcessingDetail(BaseModel):
    """Full detail for a single email's processing: original message, prompt
    used, documents included, LLM output and the log trail."""

    email_message_id: int
    mailbox_id: int
    subject: str
    sender: str
    recipients: str
    body_text: str | None
    body_html: str | None
    received_at: datetime
    prompt_template_id: int | None
    prompt_content_snapshot: str | None
    documents_used: list[str]
    web_sources_used: list[str]
    thread_context: str | None
    generated_body: str | None
    draft_id: int | None
    draft_status: str | None
    final_status: ProcessingStatus
    retry_count: int
    logs: list[ProcessingLogItem]


class SimulateDraftRequest(BaseModel):
    """An ad-hoc email body to try the agent against, without a real mailbox."""

    email_body: str = Field(..., min_length=1)


class SimulateDraftResponse(BaseModel):
    generated_body: str
    llm_provider: str
    llm_model: str
