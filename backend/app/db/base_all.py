"""Single import point that registers every model on Base.metadata.

Alembic's env.py imports this module so `alembic revision --autogenerate`
can see the full schema.
"""

from app.db.base import Base
from app.models.document import Document
from app.models.draft import Draft
from app.models.drive_source import DriveSource
from app.models.email_message import EmailMessage
from app.models.email_thread import EmailThread
from app.models.llm_trace import LLMTrace
from app.models.mailbox import Mailbox
from app.models.processing_log import ProcessingLog
from app.models.prompt import PromptTemplate
from app.models.user import User

__all__ = [
    "Base",
    "User",
    "Mailbox",
    "PromptTemplate",
    "Document",
    "EmailThread",
    "EmailMessage",
    "Draft",
    "ProcessingLog",
    "LLMTrace",
    "DriveSource",
]
