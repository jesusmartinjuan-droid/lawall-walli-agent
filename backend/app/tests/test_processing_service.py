from datetime import UTC, datetime

from app.core.encryption import encrypt_value
from app.models.document import Document
from app.models.drive_source import DriveSource
from app.models.email_message import EmailMessage
from app.models.enums import DraftStatus, MailboxProvider, ProcessingStatus
from app.models.mailbox import Mailbox
from app.services.email_provider_service import DraftCreationResult
from app.services.llm_service import LLMResponse
from app.services.processing_service import (
    AttachedFile,
    KnowledgeFileLimitExceededError,
    ProcessingService,
    _collect_attached_files,
    _derive_sources_used,
    _enforce_file_caps,
    render_prompt_template,
)


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


def _create_document(
    db_session, *, filename: str, openai_file_id: str | None, size_bytes: int = 100
) -> Document:
    document = Document(
        filename=f"stored-{filename}",
        original_filename=filename,
        content_type="application/octet-stream",
        storage_path=f"/tmp/{filename}",
        size_bytes=size_bytes,
        openai_file_id=openai_file_id,
        is_active=True,
    )
    db_session.add(document)
    db_session.commit()
    db_session.refresh(document)
    return document


def _create_drive_source(
    db_session, *, name: str, openai_file_id: str | None, size_bytes: int = 100
) -> DriveSource:
    drive_source = DriveSource(
        name=name,
        drive_url="https://drive.google.com/file/d/abc/view",
        openai_file_id=openai_file_id,
        size_bytes=size_bytes,
        is_active=True,
    )
    db_session.add(drive_source)
    db_session.commit()
    db_session.refresh(drive_source)
    return drive_source


def test_render_prompt_template_substitutes_placeholders_when_present():
    template = "Docs: {{company_documents_context}}\nThread: {{email_thread_context}}"
    rendered = render_prompt_template(
        template, company_documents_context="DOCS", email_thread_context="THREAD"
    )
    assert rendered == "Docs: DOCS\nThread: THREAD"


def test_render_prompt_template_appends_missing_placeholders_instead_of_dropping_them():
    """A prompt pasted from scratch (no {{...}} tokens at all) must still
    receive the "files are attached" note and thread history — this is the
    exact bug that left the agent blind to company knowledge for days when a
    custom prompt replaced the default one without knowing placeholders
    existed."""
    template = "Eres Walli. Responde de forma breve y profesional."

    rendered = render_prompt_template(
        template, company_documents_context="DOCS", email_thread_context="THREAD"
    )

    assert template in rendered
    assert "DOCS" in rendered
    assert "THREAD" in rendered


def test_render_prompt_template_only_appends_the_placeholder_that_is_missing():
    template = "Fuentes: {{company_documents_context}}"

    rendered = render_prompt_template(
        template, company_documents_context="DOCS", email_thread_context="THREAD"
    )

    assert rendered.count("DOCS") == 1
    assert "{{company_documents_context}}" not in rendered
    assert "THREAD" in rendered


def test_render_prompt_template_does_not_append_an_empty_value():
    template = "Eres Walli."
    rendered = render_prompt_template(template, company_documents_context="", email_thread_context="")
    assert rendered == template


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
    assert result.sources_used == []

    assert db_session.scalar(select(func.count()).select_from(EmailMessage)) == 0
    assert db_session.scalar(select(func.count()).select_from(Draft)) == 0
    assert db_session.scalar(select(func.count()).select_from(LLMTrace)) == 0
    assert db_session.scalar(select(func.count()).select_from(ProcessingLog)) == 0


def test_collect_attached_files_skips_documents_missing_an_openai_file_id(db_session):
    _create_document(db_session, filename="ready.docx", openai_file_id="file-1")
    _create_document(db_session, filename="pending.docx", openai_file_id=None)
    _create_drive_source(db_session, name="Drive OK", openai_file_id="file-2")
    _create_drive_source(db_session, name="Drive pending", openai_file_id=None)

    from app.services.document_service import DocumentService
    from app.services.drive_source_service import DriveSourceService

    documents = DocumentService(db_session).list_active_documents()
    drive_sources = DriveSourceService(db_session).list_active_drive_sources()

    attached = _collect_attached_files(documents, drive_sources)

    assert {a.name for a in attached} == {"ready.docx", "Drive OK"}


def test_enforce_file_caps_raises_when_count_exceeds_limit(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "max_knowledge_files_per_call", 1)
    attached = [
        AttachedFile(name="a.docx", openai_file_id="f1"),
        AttachedFile(name="b.docx", openai_file_id="f2"),
    ]
    documents = [
        Document(
            original_filename="a.docx", size_bytes=10, filename="a", content_type="x", storage_path="/x"
        ),
        Document(
            original_filename="b.docx", size_bytes=10, filename="b", content_type="x", storage_path="/x"
        ),
    ]

    try:
        _enforce_file_caps(attached, documents, [])
        raise AssertionError("expected KnowledgeFileLimitExceededError")
    except KnowledgeFileLimitExceededError as exc:
        assert "máximo permitido" in str(exc)


def test_enforce_file_caps_raises_when_total_bytes_exceeds_limit(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "max_knowledge_file_total_bytes", 100)
    attached = [AttachedFile(name="a.docx", openai_file_id="f1")]
    documents = [
        Document(
            original_filename="a.docx", size_bytes=1000, filename="a", content_type="x", storage_path="/x"
        )
    ]

    try:
        _enforce_file_caps(attached, documents, [])
        raise AssertionError("expected KnowledgeFileLimitExceededError")
    except KnowledgeFileLimitExceededError as exc:
        assert "tamaño total" in str(exc)


def test_derive_sources_used_finds_referenced_filename_and_web_searches():
    attached = [
        AttachedFile(name="tabla.xlsx", openai_file_id="f1"),
        AttachedFile(name="manual.docx", openai_file_id="f2"),
    ]
    code_snippets = ["import pandas as pd\npd.read_excel('tabla.xlsx')"]
    web_search_queries = ["la-wall.com plazos de entrega"]

    sources = _derive_sources_used(attached, code_snippets, web_search_queries)

    assert sources == ["tabla.xlsx", "Búsqueda web: la-wall.com plazos de entrega"]


def test_generate_and_store_draft_attaches_active_file_ids_to_the_llm_call(db_session, monkeypatch):
    document = _create_document(db_session, filename="manual.docx", openai_file_id="file-abc")
    drive_source = _create_drive_source(db_session, name="Tabla Drive", openai_file_id="file-xyz")
    mailbox = _create_mailbox(db_session)
    message = _create_email(db_session, mailbox)

    service = ProcessingService(db_session)
    captured_kwargs = {}

    def _fake_generate_draft(**kwargs):
        captured_kwargs.update(kwargs)
        return LLMResponse(
            content="Aquí tienes la respuesta.",
            provider="mock",
            model="mock-1",
            input_tokens=10,
            output_tokens=10,
            latency_ms=1,
        )

    monkeypatch.setattr(service.llm_service, "generate_draft", _fake_generate_draft)

    def fake_build_email_provider(mailbox_arg, password_arg):
        class _FakeProvider:
            def create_draft(self, *, subject, body, in_reply_to):
                return DraftCreationResult(success=True, mailbox_draft_id="1", message="ok")

        return _FakeProvider()

    monkeypatch.setattr("app.services.processing_service.build_email_provider", fake_build_email_provider)

    service.process_email(message.id)

    assert set(captured_kwargs["file_ids"]) == {document.openai_file_id, drive_source.openai_file_id}
    draft = service.drafts.get_by_email_message_id(message.id)
    assert draft.generated_body == "Aquí tienes la respuesta."
    assert draft.status == DraftStatus.CREATED_IN_MAILBOX


def test_generate_and_store_draft_fails_loudly_when_file_cap_exceeded(db_session, monkeypatch):
    from app.core.config import settings
    from app.models.enums import ProcessingLogStatus, ProcessingStep

    monkeypatch.setattr(settings, "max_knowledge_files_per_call", 1)
    _create_document(db_session, filename="a.docx", openai_file_id="file-1")
    _create_document(db_session, filename="b.docx", openai_file_id="file-2")
    mailbox = _create_mailbox(db_session)
    message = _create_email(db_session, mailbox)

    service = ProcessingService(db_session)
    service.process_email(message.id)

    assert service.drafts.get_by_email_message_id(message.id) is None
    logs = service.logs.list_for_email(message.id)
    attach_files_log = next(log for log in logs if log.step == ProcessingStep.ATTACH_FILES)
    assert attach_files_log.status == ProcessingLogStatus.FAILED
    assert "máximo permitido" in attach_files_log.error_message


def test_simulate_draft_returns_sources_used_from_the_models_tool_calls(db_session, monkeypatch):
    document = _create_document(db_session, filename="tabla.xlsx", openai_file_id="file-abc")

    service = ProcessingService(db_session)

    def _fake_generate_draft(**kwargs):
        return LLMResponse(
            content="Aquí tienes la tabla.",
            provider="mock",
            model="mock-1",
            input_tokens=10,
            output_tokens=10,
            latency_ms=1,
            code_interpreter_snippets=[f"pd.read_excel('{document.original_filename}')"],
            web_search_queries=[],
        )

    monkeypatch.setattr(service.llm_service, "generate_draft", _fake_generate_draft)

    result = service.simulate_draft("¿Qué precio tiene?")

    assert result.generated_body == "Aquí tienes la tabla."
    assert result.sources_used == ["tabla.xlsx"]


def test_simulate_draft_fails_loudly_when_file_cap_exceeded(db_session, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "max_knowledge_files_per_call", 0)
    _create_document(db_session, filename="a.docx", openai_file_id="file-1")

    service = ProcessingService(db_session)

    try:
        service.simulate_draft("¿Qué precio tiene?")
        raise AssertionError("expected KnowledgeFileLimitExceededError")
    except KnowledgeFileLimitExceededError:
        pass
