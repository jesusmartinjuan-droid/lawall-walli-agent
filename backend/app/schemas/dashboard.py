from pydantic import BaseModel

from app.schemas.processing import ProcessingListItem


class DashboardSummary(BaseModel):
    active_mailboxes: int
    total_mailboxes: int
    active_documents: int
    total_documents: int
    active_prompts: int
    total_prompts: int
    processed_emails: int
    generated_drafts: int
    recent_errors: list[ProcessingListItem]
