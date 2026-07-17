from unittest.mock import MagicMock

import app.services.mailbox_service as mailbox_service_module
from app.services.mailbox_service import MailboxService


def _create_mailbox(service: MailboxService):
    return service.create(
        imap_password="secret",
        name="Buzón test",
        email_address="soporte@example.com",
        imap_host="imap.example.com",
        imap_username="soporte@example.com",
    )


def test_first_poll_only_sets_baseline_and_fetches_nothing(db_session, monkeypatch):
    service = MailboxService(db_session)
    mailbox = _create_mailbox(service)
    assert mailbox.initial_sync_uid is None

    fake_provider = MagicMock()
    fake_provider.get_latest_uid.return_value = 42
    monkeypatch.setattr(mailbox_service_module, "build_email_provider", lambda *a, **k: fake_provider)

    result = service.poll_mailbox(mailbox, max_emails=20)

    assert result == []
    assert mailbox.initial_sync_uid == 42
    fake_provider.fetch_new_emails.assert_not_called()


def test_next_poll_fetches_only_uids_past_the_baseline(db_session, monkeypatch):
    service = MailboxService(db_session)
    mailbox = _create_mailbox(service)
    mailbox.initial_sync_uid = 42
    db_session.commit()

    fake_provider = MagicMock()
    fake_provider.fetch_new_emails.return_value = []
    monkeypatch.setattr(mailbox_service_module, "build_email_provider", lambda *a, **k: fake_provider)

    service.poll_mailbox(mailbox, max_emails=20)

    fake_provider.get_latest_uid.assert_not_called()
    _, kwargs = fake_provider.fetch_new_emails.call_args
    assert kwargs["min_uid"] == 43
