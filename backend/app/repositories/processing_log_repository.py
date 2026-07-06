from sqlalchemy import select

from app.models.processing_log import ProcessingLog
from app.repositories.base_repository import BaseRepository


class ProcessingLogRepository(BaseRepository[ProcessingLog]):
    model = ProcessingLog

    def list_for_email(self, email_message_id: int) -> list[ProcessingLog]:
        stmt = (
            select(ProcessingLog)
            .where(ProcessingLog.email_message_id == email_message_id)
            .order_by(ProcessingLog.started_at.asc())
        )
        return list(self.db.scalars(stmt).all())

    def latest_for_email(self, email_message_id: int) -> ProcessingLog | None:
        stmt = (
            select(ProcessingLog)
            .where(ProcessingLog.email_message_id == email_message_id)
            .order_by(ProcessingLog.started_at.desc())
        )
        return self.db.scalars(stmt).first()

    def count_retries_for_email(self, email_message_id: int) -> int:
        latest = self.latest_for_email(email_message_id)
        return latest.retry_count if latest else 0
