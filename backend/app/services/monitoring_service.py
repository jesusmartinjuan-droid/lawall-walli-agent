"""Aggregates the counters shown on the dashboard screen."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.draft import Draft
from app.models.email_message import EmailMessage
from app.models.mailbox import Mailbox
from app.models.prompt import PromptTemplate
from app.schemas.dashboard import DashboardSummary
from app.services.processing_service import ProcessingService


class MonitoringService:
    def __init__(self, db: Session):
        self.db = db
        self.processing_service = ProcessingService(db)

    def _count(self, model, *filters) -> int:
        stmt = select(func.count()).select_from(model)
        if filters:
            stmt = stmt.where(*filters)
        return self.db.scalar(stmt) or 0

    def get_dashboard_summary(self) -> DashboardSummary:
        recent = self.processing_service.list_processing(limit=200)
        recent_errors = [item for item in recent if item.status.value == "failed"][:10]

        return DashboardSummary(
            active_mailboxes=self._count(Mailbox, Mailbox.is_active.is_(True)),
            total_mailboxes=self._count(Mailbox),
            active_documents=self._count(Document, Document.is_active.is_(True)),
            total_documents=self._count(Document),
            active_prompts=self._count(PromptTemplate, PromptTemplate.is_active.is_(True)),
            total_prompts=self._count(PromptTemplate),
            processed_emails=self._count(EmailMessage, EmailMessage.processed_at.is_not(None)),
            generated_drafts=self._count(Draft),
            recent_errors=recent_errors,
        )
