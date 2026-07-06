"""Celery tasks: the scheduled mailbox poll, and per-email processing.

`poll_active_mailboxes` runs every MAIL_POLL_INTERVAL_SECONDS (see
scheduler.py) and fans out into one `process_email` task per newly
downloaded message, so a slow/failing LLM call for one email doesn't block
ingestion of the rest.
"""

from app.core.config import settings
from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.services.mailbox_service import MailboxService
from app.services.processing_service import ProcessingService
from app.services.web_source_service import WebSourceService
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


@celery_app.task(name="app.workers.tasks.poll_active_mailboxes")
def poll_active_mailboxes() -> None:
    db = SessionLocal()
    try:
        mailbox_service = MailboxService(db)
        active_mailboxes = mailbox_service.list_active_mailboxes()
        logger.info("worker_run_start active_mailboxes=%s", len(active_mailboxes))

        for mailbox in active_mailboxes:
            try:
                new_messages = mailbox_service.poll_mailbox(mailbox, max_emails=settings.max_emails_per_run)
            except Exception as exc:  # noqa: BLE001 - one mailbox failing must not stop the others
                logger.error("mailbox_poll_failed mailbox_id=%s error=%s", mailbox.id, exc)
                continue

            for message in new_messages:
                process_email.delay(message.id)

        logger.info("worker_run_finished active_mailboxes=%s", len(active_mailboxes))
    finally:
        db.close()


@celery_app.task(name="app.workers.tasks.process_email", bind=True, max_retries=0)
def process_email(self, email_message_id: int) -> None:
    """Retries are handled inside ProcessingService via ProcessingLog.retry_count
    (bounded by MAX_RETRY_ATTEMPTS), not via Celery's own retry mechanism, so
    that retry state is visible from the frontend."""
    db = SessionLocal()
    try:
        ProcessingService(db).process_email(email_message_id)
    finally:
        db.close()


@celery_app.task(name="app.workers.tasks.refresh_active_web_sources")
def refresh_active_web_sources() -> None:
    db = SessionLocal()
    try:
        web_source_service = WebSourceService(db)
        active_sources = web_source_service.list_active_web_sources()
        logger.info("web_source_refresh_run_start active_sources=%s", len(active_sources))

        for web_source in active_sources:
            try:
                web_source_service.refresh(web_source)
            except Exception as exc:  # noqa: BLE001 - one source failing must not stop the others
                logger.error("web_source_refresh_failed id=%s error=%s", web_source.id, exc)
                continue

        logger.info("web_source_refresh_run_finished active_sources=%s", len(active_sources))
    finally:
        db.close()
