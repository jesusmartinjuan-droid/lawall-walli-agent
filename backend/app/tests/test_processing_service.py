import io
from datetime import UTC, datetime

from PIL import Image

from app.core.encryption import encrypt_value
from app.models.email_message import EmailMessage
from app.models.enums import DraftStatus, MailboxProvider, ProcessingStatus
from app.models.mailbox import Mailbox
from app.services.agent_image_service import AgentImageService
from app.services.email_provider_service import DraftCreationResult
from app.services.processing_service import ProcessingService, render_prompt_template


def _png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (10, 10), color=(200, 50, 50)).save(buffer, format="PNG")
    return buffer.getvalue()


def _create_agent_image(db_session, *, name: str, description: str):
    return AgentImageService(db_session).create(
        name=name, description=description, original_filename="tabla.png", file_bytes=_png_bytes()
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


def test_render_prompt_template_substitutes_placeholders_when_present():
    template = "Docs: {{company_documents_context}}\nThread: {{email_thread_context}}"
    rendered = render_prompt_template(
        template, company_documents_context="DOCS", email_thread_context="THREAD"
    )
    assert rendered == "Docs: DOCS\nThread: THREAD"


def test_render_prompt_template_appends_missing_placeholders_instead_of_dropping_them():
    """A prompt pasted from scratch (no {{...}} tokens at all) must still
    receive the knowledge base and thread history — this is the exact bug
    that left the agent blind to company knowledge for days when a custom
    prompt replaced the default one without knowing placeholders existed."""
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
            def create_draft(self, *, subject, body, in_reply_to, inline_image=None):
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


def test_build_agent_image_selection_lists_available_images():
    from app.services.processing_service import _build_agent_image_selection

    class _FakeImage:
        def __init__(self, name, description):
            self.name = name
            self.description = description

    images = [_FakeImage("Tabla ES", "Usar en español."), _FakeImage("Tabla EN", "Use in English.")]
    schema_property, note = _build_agent_image_selection(images)

    assert schema_property["enum"] == ["Tabla ES", "Tabla EN", "ninguna"]
    assert "Tabla ES: Usar en español." in note
    assert "Tabla EN: Use in English." in note


def test_build_agent_image_selection_with_no_images_only_offers_none():
    from app.services.processing_service import _build_agent_image_selection

    schema_property, note = _build_agent_image_selection([])

    assert schema_property["enum"] == ["ninguna"]
    assert note == ""


def test_parse_draft_with_image_extracts_the_chosen_image():
    import json

    from app.services.processing_service import _parse_draft_with_image

    raw = json.dumps({"draft": "Hola,\n\nAquí tienes la tabla.", "image_name": "Tabla ES"})
    draft, image_name = _parse_draft_with_image(raw)

    assert draft == "Hola,\n\nAquí tienes la tabla."
    assert image_name == "Tabla ES"


def test_parse_draft_with_image_treats_ninguna_as_no_image():
    import json

    from app.services.processing_service import _parse_draft_with_image

    raw = json.dumps({"draft": "Hola.", "image_name": "ninguna"})
    draft, image_name = _parse_draft_with_image(raw)

    assert draft == "Hola."
    assert image_name is None


def test_parse_draft_with_image_falls_back_to_raw_text_on_invalid_json():
    from app.services.processing_service import _parse_draft_with_image

    draft, image_name = _parse_draft_with_image("Esto no es JSON.")

    assert draft == "Esto no es JSON."
    assert image_name is None


def test_generate_and_store_draft_attaches_the_image_the_model_chooses(db_session, monkeypatch):
    import json

    from app.services.llm_service import LLMResponse

    mailbox = _create_mailbox(db_session)
    message = _create_email(db_session, mailbox)
    image = _create_agent_image(
        db_session, name="Tabla ES", description="Usar cuando pregunten por precios en español."
    )

    service = ProcessingService(db_session)
    captured_kwargs = {}

    def _fake_generate_draft(**kwargs):
        captured_kwargs.update(kwargs)
        content = json.dumps({"draft": "Aquí tienes la tabla de precios.", "image_name": "Tabla ES"})
        return LLMResponse(
            content=content,
            provider="mock",
            model="mock-1",
            input_tokens=10,
            output_tokens=10,
            latency_ms=1,
        )

    monkeypatch.setattr(service.llm_service, "generate_draft", _fake_generate_draft)

    def fake_build_email_provider(mailbox_arg, password_arg):
        class _FakeProvider:
            def create_draft(self, *, subject, body, in_reply_to, inline_image=None):
                assert inline_image is not None
                assert inline_image.content_type == "image/png"
                return DraftCreationResult(success=True, mailbox_draft_id="1", message="ok")

        return _FakeProvider()

    monkeypatch.setattr("app.services.processing_service.build_email_provider", fake_build_email_provider)

    service.process_email(message.id)

    draft = service.drafts.get_by_email_message_id(message.id)
    assert draft.agent_image_id == image.id
    assert draft.generated_body == "Aquí tienes la tabla de precios."
    assert captured_kwargs["response_schema"] is not None
    assert draft.status == DraftStatus.CREATED_IN_MAILBOX


def test_generate_and_store_draft_sets_no_image_when_model_chooses_ninguna(db_session, monkeypatch):
    import json

    from app.services.llm_service import LLMResponse

    mailbox = _create_mailbox(db_session)
    message = _create_email(db_session, mailbox)
    _create_agent_image(db_session, name="Tabla ES", description="Usar en español.")

    service = ProcessingService(db_session)

    def _fake_generate_draft(**kwargs):
        content = json.dumps({"draft": "Gracias por tu consulta.", "image_name": "ninguna"})
        return LLMResponse(
            content=content,
            provider="mock",
            model="mock-1",
            input_tokens=10,
            output_tokens=10,
            latency_ms=1,
        )

    monkeypatch.setattr(service.llm_service, "generate_draft", _fake_generate_draft)

    def fake_build_email_provider(mailbox_arg, password_arg):
        class _FakeProvider:
            def create_draft(self, *, subject, body, in_reply_to, inline_image=None):
                assert inline_image is None
                return DraftCreationResult(success=True, mailbox_draft_id="1", message="ok")

        return _FakeProvider()

    monkeypatch.setattr("app.services.processing_service.build_email_provider", fake_build_email_provider)

    service.process_email(message.id)

    draft = service.drafts.get_by_email_message_id(message.id)
    assert draft.agent_image_id is None


def test_load_inline_image_degrades_gracefully_when_image_was_deleted(db_session):
    from app.models.draft import Draft

    mailbox = _create_mailbox(db_session)
    message = _create_email(db_session, mailbox)
    image = _create_agent_image(db_session, name="Tabla ES", description="...")

    service = ProcessingService(db_session)
    draft = Draft(
        mailbox_id=mailbox.id,
        email_message_id=message.id,
        agent_image_id=image.id,
        generated_body="Hola",
        llm_provider="mock",
        llm_model="mock-1",
        status=DraftStatus.GENERATED,
    )
    service.drafts.add(draft)
    service.drafts.commit()

    service.agent_image_service.delete(image.id)

    assert service._load_inline_image(draft) is None


def test_simulate_draft_returns_the_attached_image_the_model_chooses(db_session, monkeypatch):
    import json

    from app.services.llm_service import LLMResponse

    image = _create_agent_image(db_session, name="Tabla ES", description="Usar en español.")
    service = ProcessingService(db_session)

    def _fake_generate_draft(**kwargs):
        content = json.dumps({"draft": "Aquí tienes la tabla.", "image_name": "Tabla ES"})
        return LLMResponse(
            content=content,
            provider="mock",
            model="mock-1",
            input_tokens=10,
            output_tokens=10,
            latency_ms=1,
        )

    monkeypatch.setattr(service.llm_service, "generate_draft", _fake_generate_draft)

    result = service.simulate_draft("¿Qué precio tiene?")

    assert result.generated_body == "Aquí tienes la tabla."
    assert result.attached_image_id == image.id
    assert result.attached_image_name == "Tabla ES"


def test_generate_and_store_draft_skips_image_selection_when_disabled(db_session, monkeypatch):
    from app.core.config import settings

    mailbox = _create_mailbox(db_session)
    message = _create_email(db_session, mailbox)
    _create_agent_image(db_session, name="Tabla ES", description="...")
    monkeypatch.setattr(settings, "enable_agent_image_embedding", False)

    service = ProcessingService(db_session)
    captured_kwargs = {}
    original_generate_draft = service.llm_service.generate_draft

    def _spy_generate_draft(**kwargs):
        captured_kwargs.update(kwargs)
        return original_generate_draft(**kwargs)

    monkeypatch.setattr(service.llm_service, "generate_draft", _spy_generate_draft)

    def fake_build_email_provider(mailbox_arg, password_arg):
        class _FakeProvider:
            def create_draft(self, *, subject, body, in_reply_to, inline_image=None):
                assert inline_image is None
                return DraftCreationResult(success=True, mailbox_draft_id="1", message="ok")

        return _FakeProvider()

    monkeypatch.setattr("app.services.processing_service.build_email_provider", fake_build_email_provider)

    service.process_email(message.id)

    assert captured_kwargs["response_schema"] is None
    draft = service.drafts.get_by_email_message_id(message.id)
    assert draft.agent_image_id is None


def test_parse_simulator_output_extracts_draft_image_and_citations():
    import json

    from app.services.processing_service import _parse_simulator_output

    raw = json.dumps(
        {
            "draft": "Hola, aquí tienes tu respuesta.",
            "image_name": "ninguna",
            "citations": [
                {
                    "source": "### Manual Maestro",
                    "excerpt": "250 metros se interpretan como metros cuadrados.",
                },
                {"source": "Condiciones Generales", "excerpt": "El molde sigue siendo propiedad de laWALL."},
            ],
        }
    )
    body, image_name, citations = _parse_simulator_output(raw)

    assert body == "Hola, aquí tienes tu respuesta."
    assert image_name is None
    assert [(c.source, c.excerpt) for c in citations] == [
        ("Manual Maestro", "250 metros se interpretan como metros cuadrados."),
        ("Condiciones Generales", "El molde sigue siendo propiedad de laWALL."),
    ]


def test_parse_simulator_output_extracts_the_chosen_image():
    import json

    from app.services.processing_service import _parse_simulator_output

    raw = json.dumps({"draft": "Aquí tienes la tabla.", "image_name": "Tabla ES", "citations": []})
    body, image_name, citations = _parse_simulator_output(raw)

    assert body == "Aquí tienes la tabla."
    assert image_name == "Tabla ES"
    assert citations == []


def test_parse_simulator_output_falls_back_to_raw_text_on_invalid_json():
    from app.services.processing_service import _parse_simulator_output

    body, image_name, citations = _parse_simulator_output("Esto no es JSON en absoluto.")

    assert body == "Esto no es JSON en absoluto."
    assert image_name is None
    assert citations == []


def test_parse_simulator_output_ignores_incomplete_citation_entries():
    import json

    from app.services.processing_service import _parse_simulator_output

    raw = json.dumps(
        {
            "draft": "Hola.",
            "image_name": "ninguna",
            "citations": [{"source": "Manual Maestro"}, {"excerpt": "sin fuente"}, {}],
        }
    )
    body, image_name, citations = _parse_simulator_output(raw)

    assert body == "Hola."
    assert citations == []


def test_filter_verified_citations_drops_excerpts_not_present_in_the_context():
    from app.schemas.processing import SourceCitation
    from app.services.processing_service import _filter_verified_citations

    context = "### Manual Maestro\n250 metros se interpretan como metros cuadrados.\n"
    citations = [
        SourceCitation(source="Manual Maestro", excerpt="250 metros se interpretan como metros cuadrados."),
        SourceCitation(source="Manual Maestro", excerpt="Esto no aparece en ningún sitio."),
    ]

    kept = _filter_verified_citations(citations, context)

    assert [(c.source, c.excerpt) for c in kept] == [
        ("Manual Maestro", "250 metros se interpretan como metros cuadrados.")
    ]


def test_filter_verified_citations_tolerates_minor_rewording_by_the_model():
    from app.schemas.processing import SourceCitation
    from app.services.processing_service import _filter_verified_citations

    context = "El molde fabricado por encargo del cliente sigue siendo propiedad de laWALL."
    citations = [
        SourceCitation(
            source="Condiciones",
            # Model added "es y" while quoting — a single small rewording,
            # not a fabrication.
            excerpt="El molde fabricado por encargo del cliente es y sigue siendo propiedad de laWALL.",
        ),
    ]

    kept = _filter_verified_citations(citations, context)

    assert len(kept) == 1


def test_filter_verified_citations_still_drops_mostly_invented_excerpts():
    from app.schemas.processing import SourceCitation
    from app.services.processing_service import _filter_verified_citations

    context = "El molde fabricado por encargo del cliente sigue siendo propiedad de laWALL."
    citations = [
        SourceCitation(
            source="Condiciones",
            excerpt="laWALL garantiza la exclusividad del diseño durante cinco años tras la entrega.",
        ),
    ]

    kept = _filter_verified_citations(citations, context)

    assert kept == []


def test_simulate_draft_drops_citations_that_cannot_be_verified(db_session):
    import json

    from app.services.llm_service import LLMResponse

    service = ProcessingService(db_session)
    canned = json.dumps(
        {
            "draft": "Hola,\n\nGracias por tu consulta.",
            "image_name": "ninguna",
            "citations": [
                {"source": "Manual Maestro", "excerpt": "esto no está en la base de conocimiento activa"}
            ],
        }
    )
    captured_kwargs = {}

    def _fake_generate_draft(**kwargs):
        captured_kwargs.update(kwargs)
        return LLMResponse(
            content=canned, provider="mock", model="mock-1", input_tokens=10, output_tokens=10, latency_ms=1
        )

    service.llm_service.generate_draft = _fake_generate_draft

    result = service.simulate_draft("¿Qué tamaño tienen las planchas?")

    assert captured_kwargs["response_schema"] is not None
    assert result.generated_body == "Hola,\n\nGracias por tu consulta."
    # No active documents/sources are loaded in this test's DB, so the
    # self-reported excerpt can never verify against an (empty) knowledge
    # context and must be dropped rather than shown as unreliable.
    assert result.sources_used == []
