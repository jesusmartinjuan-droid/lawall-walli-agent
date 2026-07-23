from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import MailboxProvider

# Plain `str` rather than EmailStr: internal/staging mailboxes may live on
# non-public or special-use domains that email-validator would reject.


class MailboxBase(BaseModel):
    name: str
    email_address: str
    provider: MailboxProvider = MailboxProvider.NOMINALIA
    imap_host: str
    imap_port: int = 993
    imap_username: str
    imap_use_ssl: bool = True
    inbox_folder: str = "INBOX"
    drafts_folder: str = "Drafts"


class MailboxCreate(MailboxBase):
    imap_password: str = Field(..., description="Plain password, encrypted before storage.")


class MailboxUpdate(BaseModel):
    name: str | None = None
    email_address: str | None = None
    provider: MailboxProvider | None = None
    imap_host: str | None = None
    imap_port: int | None = None
    imap_username: str | None = None
    imap_password: str | None = Field(default=None, description="Only sent when the password changes.")
    imap_use_ssl: bool | None = None
    inbox_folder: str | None = None
    drafts_folder: str | None = None
    is_active: bool | None = None


class MailboxResponse(MailboxBase):
    id: int
    is_active: bool
    last_checked_at: datetime | None
    last_poll_error: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MailboxTestConnectionResponse(BaseModel):
    success: bool
    message: str
