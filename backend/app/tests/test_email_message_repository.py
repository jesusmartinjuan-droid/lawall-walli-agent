from datetime import UTC, datetime

from app.core.encryption import encrypt_value
from app.models.email_message import EmailMessage
from app.models.enums import MailboxProvider
from app.models.mailbox import Mailbox
from app.repositories.email_repository import EmailMessageRepository


def _create_mailbox(db_session) -> Mailbox:
    mailbox = Mailbox(
        name="Soporte",
        email_address="soporte@lawall.local",
        provider=MailboxProvider.NOMINALIA,
        imap_host="imap.nominalia.test",
        imap_port=993,
        imap_username="soporte@lawall.local",
        encrypted_imap_password=encrypt_value("secret"),
        imap_use_ssl=True,
    )
    db_session.add(mailbox)
    db_session.commit()
    db_session.refresh(mailbox)
    return mailbox


def test_exists_by_uid_detects_duplicates(db_session):
    mailbox = _create_mailbox(db_session)
    repo = EmailMessageRepository(db_session)

    assert repo.exists_by_uid(mailbox.id, 101) is False

    message = EmailMessage(
        mailbox_id=mailbox.id,
        thread_id=None,
        external_message_id="<msg-1@example.com>",
        imap_uid=101,
        sender="cliente@example.com",
        recipients=mailbox.email_address,
        subject="Consulta",
        body_text="Hola",
        received_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )
    db_session.add(message)
    db_session.commit()

    assert repo.exists_by_uid(mailbox.id, 101) is True
    assert repo.exists_by_external_message_id(mailbox.id, "<msg-1@example.com>") is True
    assert repo.exists_by_external_message_id(mailbox.id, "<other@example.com>") is False
