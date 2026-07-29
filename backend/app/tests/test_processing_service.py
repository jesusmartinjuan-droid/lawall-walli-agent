from datetime import UTC, datetime

from app.core.encryption import encrypt_value
from app.models.email_message import EmailMessage
from app.models.enums import DraftStatus, MailboxProvider, ProcessingStatus
from app.models.mailbox import Mailbox
from app.services.email_provider_service import DraftCreationResult
from app.services.processing_service import ProcessingService, render_prompt_template


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


def _create_email(db_session, mailbox: Mailbox) -> EmailMessage:
    message = EmailMessage(
        mailbox_id=mailbox.id,
        thread_id=None,
        external_message_id="<msg-1@example.com>",
        imap_uid=1,
        sender="cliente@example.com",
        recipients=mailbox.email_address,
        subject="Consulta sobre precios",
        body_text="Hola, ¿cuál es el precio del servicio?",
        received_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )
    db_session.add(message)
    db_session.commit()
    db_session.refresh(message)
    return message


def test_render_prompt_template_substitutes_all_placeholders():
    template = "Docs: {{company_documents_context}}\nEmail: {{email_body}}\nThread: {{email_thread_context}}"
    rendered = render_prompt_template(
        template,
        company_documents_context="DOCS",
        email_body="EMAIL",
        email_thread_context="THREAD",
    )
    assert rendered == "Docs: DOCS\nEmail: EMAIL\nThread: THREAD"


def test_process_email_generates_draft_with_mock_llm_and_handles_mailbox_failure(db_session, monkeypatch):
    mailbox = _create_mailbox(db_session)
    message = _create_email(db_session, mailbox)

    def fake_build_email_provider(mailbox_arg, password_arg):
        class _FakeProvider:
            def create_draft(self, *, subject, body, in_reply_to):
                return DraftCreationResult(success=False, mailbox_draft_id=None, message="Not supported.")

        return _FakeProvider()

    monkeypatch.setattr("app.services.processing_service.build_email_provider", fake_build_email_provider)

    service = ProcessingService(db_session)
    service.process_email(message.id)

    draft = service.drafts.get_by_email_message_id(message.id)
    assert draft is not None
    assert draft.status == DraftStatus.FAILED_TO_CREATE_IN_MAILBOX
    assert draft.generated_body

    detail = service.get_processing_detail(message.id)
    assert detail is not None
    assert detail.final_status == ProcessingStatus.DRAFT_GENERATED

    list_item = service.list_processing()[0]
    assert list_item.status == ProcessingStatus.DRAFT_GENERATED
    assert list_item.draft_id == draft.id


def test_process_email_respects_max_retry_attempts(db_session, monkeypatch):
    from app.core.config import settings
    from app.models.enums import ProcessingLogStatus, ProcessingStep
    from app.models.processing_log import ProcessingLog

    mailbox = _create_mailbox(db_session)
    message = _create_email(db_session, mailbox)

    for _ in range(settings.max_retry_attempts):
        log = ProcessingLog(
            mailbox_id=mailbox.id,
            email_message_id=message.id,
            draft_id=None,
            status=ProcessingLogStatus.RETRYING,
            step=ProcessingStep.FINALIZE,
            retry_count=settings.max_retry_attempts,
        )
        db_session.add(log)
    db_session.commit()

    service = ProcessingService(db_session)
    service.process_email(message.id)

    assert service.drafts.get_by_email_message_id(message.id) is None
    latest_log = service.logs.latest_for_email(message.id)
    assert latest_log.status == ProcessingLogStatus.IGNORED


def test_simulate_draft_returns_generated_text_without_persisting_anything(db_session):
    from sqlalchemy import func, select

    from app.models.draft import Draft
    from app.models.llm_trace import LLMTrace
    from app.models.processing_log import ProcessingLog

    service = ProcessingService(db_session)
    result = service.simulate_draft("Hola, ¿tenéis disponibilidad para la próxima semana?")

    assert result.generated_body
    assert result.llm_provider == "mock"
    assert result.llm_model == "mock-1"

    assert db_session.scalar(select(func.count()).select_from(EmailMessage)) == 0
    assert db_session.scalar(select(func.count()).select_from(Draft)) == 0
    assert db_session.scalar(select(func.count()).select_from(LLMTrace)) == 0
    assert db_session.scalar(select(func.count()).select_from(ProcessingLog)) == 0
