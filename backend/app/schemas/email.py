from datetime import datetime

from pydantic import BaseModel

from app.models.enums import EmailThreadStatus


class EmailMessageResponse(BaseModel):
    id: int
    mailbox_id: int
    thread_id: int | None
    sender: str
    recipients: str
    subject: str
    body_text: str | None
    body_html: str | None
    received_at: datetime
    processed_at: datetime | None

    model_config = {"from_attributes": True}


class EmailThreadResponse(BaseModel):
    id: int
    mailbox_id: int
    external_thread_id: str
    subject: str
    customer_email: str
    status: EmailThreadStatus

    model_config = {"from_attributes": True}
