"""Mailbox CRUD, credential encryption, connection testing and inbox polling.

Polling (`poll_mailbox`) is the entry point the worker calls once per minute
per active mailbox: it downloads new messages via the appropriate
`EmailProvider` and persists them as `EmailMessage`/`EmailThread` rows,
de-duplicating via the unique (mailbox_id, imap_uid) and
(mailbox_id, external_message_id) constraints. The very first poll for a
mailbox only records `initial_sync_uid` (the current highest UID) and fetches
nothing, so a newly connected mailbox never imports its pre-existing history.
"""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.encryption import decrypt_value, encrypt_value
from app.core.logging import get_logger
from app.models.email_message import EmailMessage
from app.models.email_thread import EmailThread
from app.models.enums import MailboxProvider
from app.models.mailbox import Mailbox
from app.repositories.email_repository import EmailMessageRepository, EmailThreadRepository
from app.repositories.mailbox_repository import MailboxRepository
from app.services.email_provider_service import (
    EmailProvider,
    FetchedEmail,
    ImapCredentials,
    ImapEmailProvider,
)
from app.services.nominalia_email_provider import NominaliaEmailProvider

logger = get_logger(__name__)


def build_email_provider(mailbox: Mailbox, plain_password: str) -> EmailProvider:
    credentials = ImapCredentials(
        host=mailbox.imap_host,
        port=mailbox.imap_port,
        username=mailbox.imap_username,
        password=plain_password,
        use_ssl=mailbox.imap_use_ssl,
        inbox_folder=mailbox.inbox_folder,
        drafts_folder=mailbox.drafts_folder,
    )
    if mailbox.provider == MailboxProvider.NOMINALIA:
        return NominaliaEmailProvider(credentials)
    return ImapEmailProvider(credentials)


class MailboxService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = MailboxRepository(db)
        self.threads = EmailThreadRepository(db)
        self.messages = EmailMessageRepository(db)

    # --- CRUD -----------------------------------------------------------
    def list_mailboxes(self) -> list[Mailbox]:
        return self.repo.list(limit=500)

    def list_active_mailboxes(self) -> list[Mailbox]:
        return self.repo.list_active()

    def get(self, mailbox_id: int) -> Mailbox | None:
        return self.repo.get(mailbox_id)

    def create(self, *, imap_password: str, **fields) -> Mailbox:
        mailbox = Mailbox(encrypted_imap_password=encrypt_value(imap_password), **fields)
        self.repo.add(mailbox)
        self.repo.commit()
        logger.info("mailbox_created id=%s email=%s", mailbox.id, mailbox.email_address)
        return mailbox

    def update(self, mailbox: Mailbox, *, imap_password: str | None = None, **fields) -> Mailbox:
        for key, value in fields.items():
            if value is not None:
                setattr(mailbox, key, value)
        if imap_password:
            mailbox.encrypted_imap_password = encrypt_value(imap_password)
        self.repo.commit()
        self.repo.refresh(mailbox)
        return mailbox

    def delete(self, mailbox: Mailbox) -> None:
        self.repo.delete(mailbox)
        self.repo.commit()

    def set_active(self, mailbox: Mailbox, is_active: bool) -> Mailbox:
        mailbox.is_active = is_active
        self.repo.commit()
        self.repo.refresh(mailbox)
        logger.info("mailbox_active_flag_changed id=%s is_active=%s", mailbox.id, is_active)
        return mailbox

    # --- Connection / credentials ---------------------------------------
    def decrypt_password(self, mailbox: Mailbox) -> str:
        return decrypt_value(mailbox.encrypted_imap_password)

    def test_connection(self, mailbox: Mailbox) -> tuple[bool, str]:
        provider = build_email_provider(mailbox, self.decrypt_password(mailbox))
        return provider.test_connection()

    # --- Polling / ingestion --------------------------------------------
    def poll_mailbox(self, mailbox: Mailbox, max_emails: int) -> list[EmailMessage]:
        """Fetch new emails for `mailbox`, persist them, and return the newly
        created `EmailMessage` rows (ready to be handed to ProcessingService)."""
        provider = build_email_provider(mailbox, self.decrypt_password(mailbox))

        if mailbox.initial_sync_uid is None:
            # First poll for this mailbox: only record the current highest UID
            # as the sync baseline, don't import anything yet. This is what
            # keeps a newly connected mailbox from dumping its entire history
            # into Walli — from the next poll onward we only fetch UIDs past
            # this point.
            try:
                mailbox.initial_sync_uid = provider.get_latest_uid()
                mailbox.last_poll_error = None
            except Exception as exc:
                logger.error("mailbox_initial_sync_baseline_failed mailbox_id=%s error=%s", mailbox.id, exc)
                mailbox.last_poll_error = str(exc)
                raise
            finally:
                mailbox.last_checked_at = datetime.now(UTC)
                self.repo.commit()
            logger.info(
                "mailbox_initial_sync_baseline_set mailbox_id=%s uid=%s", mailbox.id, mailbox.initial_sync_uid
            )
            return []

        known_uids = self._known_uids(mailbox.id)
        try:
            fetched_emails = provider.fetch_new_emails(
                known_uids, max_emails, min_uid=mailbox.initial_sync_uid + 1
            )
            mailbox.last_poll_error = None
        except Exception as exc:
            logger.error("mailbox_poll_imap_error mailbox_id=%s error=%s", mailbox.id, exc)
            mailbox.last_poll_error = str(exc)
            raise
        finally:
            mailbox.last_checked_at = datetime.now(UTC)
            self.repo.commit()

        new_messages: list[EmailMessage] = []
        for fetched in fetched_emails:
            if self.messages.exists_by_uid(mailbox.id, fetched.imap_uid):
                logger.info("email_skipped_duplicate_uid mailbox_id=%s uid=%s", mailbox.id, fetched.imap_uid)
                continue
            if self.messages.exists_by_external_message_id(mailbox.id, fetched.external_message_id):
                logger.info(
                    "email_skipped_duplicate_message_id mailbox_id=%s message_id=%s",
                    mailbox.id,
                    fetched.external_message_id,
                )
                continue

            message = self._persist_message(mailbox, fetched)
            new_messages.append(message)

        logger.info(
            "mailbox_polled mailbox_id=%s fetched=%s new=%s",
            mailbox.id,
            len(fetched_emails),
            len(new_messages),
        )
        return new_messages

    def _known_uids(self, mailbox_id: int) -> set[int]:
        from sqlalchemy import select

        stmt = select(EmailMessage.imap_uid).where(EmailMessage.mailbox_id == mailbox_id)
        return set(self.db.scalars(stmt).all())

    def _persist_message(self, mailbox: Mailbox, fetched: FetchedEmail) -> EmailMessage:
        thread = None
        if fetched.external_thread_id:
            thread = self.threads.get_by_external_id(mailbox.id, fetched.external_thread_id)
            if thread is None:
                thread = EmailThread(
                    mailbox_id=mailbox.id,
                    external_thread_id=fetched.external_thread_id,
                    subject=fetched.subject,
                    customer_email=fetched.sender,
                )
                self.threads.add(thread)

        message = EmailMessage(
            mailbox_id=mailbox.id,
            thread_id=thread.id if thread else None,
            external_message_id=fetched.external_message_id,
            imap_uid=fetched.imap_uid,
            sender=fetched.sender,
            recipients=fetched.recipients,
            subject=fetched.subject,
            body_text=fetched.body_text,
            body_html=fetched.body_html,
            received_at=fetched.received_at,
            created_at=datetime.now(UTC),
        )
        self.messages.add(message)
        self.repo.commit()
        self.repo.refresh(message)
        return message
