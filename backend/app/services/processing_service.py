"""Orchestrates turning one downloaded email into a reviewable draft.

`process_email` is the single entry point the Celery task calls for each new
`EmailMessage`. It is responsible for:
  1. Loading the active prompt and active documents.
  2. Building the LLM context (knowledge base + thread history).
  3. Calling the LLM and persisting the resulting `Draft` + `LLMTrace`.
  4. Attempting to write the draft back into the mailbox.
  5. Recording a `ProcessingLog` row per step, so the frontend can show a full
     trail, and tracking retries so a failing email is not reprocessed forever.

The other public methods (`list_processing`, `get_processing_detail`) back the
draft-history and processing-detail screens.
"""

import difflib
import json
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.encryption import decrypt_value
from app.core.logging import get_logger
from app.models.agent_image import AgentImage
from app.models.draft import Draft
from app.models.email_message import EmailMessage
from app.models.enums import DraftStatus, ProcessingLogStatus, ProcessingStatus, ProcessingStep
from app.models.llm_trace import LLMTrace
from app.models.processing_log import ProcessingLog
from app.repositories.draft_repository import DraftRepository
from app.repositories.email_repository import EmailMessageRepository, EmailThreadRepository
from app.repositories.llm_trace_repository import LLMTraceRepository
from app.repositories.mailbox_repository import MailboxRepository
from app.repositories.processing_log_repository import ProcessingLogRepository
from app.schemas.processing import (
    ProcessingDetail,
    ProcessingListItem,
    SimulateDraftResponse,
    SourceCitation,
)
from app.services.agent_image_service import AgentImageService
from app.services.document_service import DocumentService
from app.services.email_provider_service import FetchedEmail, InlineImage
from app.services.knowledge_context_service import KnowledgeContextService
from app.services.llm_service import LLMProviderError, LLMService
from app.services.mailbox_service import build_email_provider
from app.services.prompt_service import PromptService
from app.services.web_source_service import WebSourceService

logger = get_logger(__name__)


_KNOWLEDGE_PLACEHOLDER = "{{company_documents_context}}"
_THREAD_PLACEHOLDER = "{{email_thread_context}}"


def render_prompt_template(
    template: str, *, company_documents_context: str, email_thread_context: str
) -> str:
    """Injects the knowledge base and thread history into the prompt template.

    A prompt author can place `{{company_documents_context}}` /
    `{{email_thread_context}}` anywhere in the template for exact control
    over where they appear. If a placeholder is absent — e.g. someone pastes
    a brand new prompt without knowing these exist — the corresponding block
    is appended at the end instead of silently dropped, so the model never
    loses access to company knowledge or thread history just because the
    template didn't ask for it explicitly.

    The customer email itself has no placeholder: it's always sent as the
    separate user-role message (see `ProcessingService`), so it can't be lost
    this way and doesn't need to be repeated here.
    """
    rendered = _inject(template, _KNOWLEDGE_PLACEHOLDER, "FUENTES VIGENTES", company_documents_context)
    rendered = _inject(
        rendered, _THREAD_PLACEHOLDER, "HILO ANTERIOR DE LA CONVERSACIÓN", email_thread_context
    )
    return rendered


def _inject(template: str, placeholder: str, fallback_title: str, value: str) -> str:
    if placeholder in template:
        return template.replace(placeholder, value)
    if not value:
        return template
    return f"{template}\n\n--- {fallback_title} ---\n{value}"


_NO_IMAGE = "ninguna"

_SOURCE_ATTRIBUTION_NOTE = """

============================================================
NOTA SOLO PARA ESTA PRUEBA (no forma parte del prompt real; nunca la apliques a un correo de verdad)
============================================================

Además del borrador, debes devolver, por cada afirmación concreta que se apoye en una fuente, el \
nombre exacto de esa fuente (tal y como aparece precedido de "###" entre las fuentes vigentes) y un \
fragmento literal, textual, de una o dos frases, copiado tal cual de esa fuente — nunca lo \
parafrasees ni lo inventes. Si no te has apoyado en ninguna fuente concreta, deja esa lista vacía.
"""

_DRAFT_FIELD_SCHEMA = {
    "type": "string",
    "description": (
        "El borrador de respuesta para el cliente, exactamente como se entregaría. Si "
        '`image_name` no es "ninguna", NO escribas de nuevo en texto los datos que esa '
        "imagen ya muestra (p. ej. un desglose de precios por m²) — mostrar la imagen ya "
        "cumple cualquier obligación de incluir ese dato, no hace falta repetirlo."
    ),
}

_CITATIONS_FIELD_SCHEMA = {
    "type": "array",
    "description": "Fuentes concretas usadas para fundamentar el borrador, con su cita literal.",
    "items": {
        "type": "object",
        "properties": {
            "source": {
                "type": "string",
                "description": 'Nombre exacto de la fuente, tal y como aparece precedido de "###".',
            },
            "excerpt": {
                "type": "string",
                "description": "Fragmento literal, copiado tal cual de esa fuente.",
            },
        },
        "required": ["source", "excerpt"],
        "additionalProperties": False,
    },
}


def _build_draft_schema(image_schema_property: dict) -> dict:
    """The structured-output schema for real draft generation: which
    configured image (if any) to attach, plus the draft text. Deciding
    `image_name` FIRST (schema property order) lets the model condition the
    draft text on that decision — e.g. skip repeating a price breakdown in
    text once it has already committed to attaching the image that shows it
    — rather than writing the draft and only separately, disconnectedly,
    deciding on an image afterward. The `image_name` enum comes from
    whatever images staff currently have set up — see
    `_build_agent_image_selection` — so this is never a fixed constant."""
    return {
        "type": "object",
        "properties": {
            "image_name": image_schema_property,
            "draft": _DRAFT_FIELD_SCHEMA,
        },
        "required": ["image_name", "draft"],
        "additionalProperties": False,
    }


def _build_simulator_schema(image_schema_property: dict) -> dict:
    """The Simulador's structured-output schema: same image-selection as
    real generation, plus the source citations behind the draft — richer
    than `_build_draft_schema` since the Simulador is also where staff
    verify *why* the agent answered as it did, not just preview the email."""
    return {
        "type": "object",
        "properties": {
            "image_name": image_schema_property,
            "draft": _DRAFT_FIELD_SCHEMA,
            "citations": _CITATIONS_FIELD_SCHEMA,
        },
        "required": ["image_name", "draft", "citations"],
        "additionalProperties": False,
    }


def _build_agent_image_selection(images: list[AgentImage]) -> tuple[dict, str]:
    """Builds the JSON-schema property + system note for choosing which
    configured image (if any) to embed in this specific reply, from the
    images staff currently have set up. Shared by real draft generation and
    the Simulador so both exercise identical, always-current behavior — an
    image added, renamed or removed from the "Imágenes del agente" screen
    takes effect on the very next email, no code change or redeploy.
    """
    enum_values = [image.name for image in images] + [_NO_IMAGE]
    schema_property = {
        "type": "string",
        "enum": enum_values,
        "description": (
            'Nombre EXACTO de la imagen a adjuntar si corresponde, o "ninguna" si no aplica ninguna.'
        ),
    }
    if not images:
        return schema_property, ""

    lines = "\n".join(f"- {image.name}: {image.description}" for image in images)
    note = f"""

============================================================
IMÁGENES DISPONIBLES PARA ADJUNTAR (elige el nombre EXACTO en "image_name" si corresponde, o "{_NO_IMAGE}")
============================================================
{lines}
"""
    return schema_property, note


def _parse_draft_with_image(raw: str) -> tuple[str, str | None]:
    """Parses the {"image_name": ..., "draft": ...} structured output (real
    generation) into (draft_text, chosen_image_name_or_None). Falls back to
    (raw, None) if the response isn't valid JSON (e.g. a provider that
    ignores `response_schema`), so a malformed response never breaks
    generation — it just means no image gets attached."""
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return raw.strip(), None
    if not isinstance(payload, dict):
        return raw.strip(), None

    draft = str(payload.get("draft", raw)).strip()
    image_name = payload.get("image_name")
    if not image_name or image_name == _NO_IMAGE:
        image_name = None
    return draft, image_name


def _parse_simulator_output(raw: str) -> tuple[str, str | None, list[SourceCitation]]:
    """Parses the Simulador's {"image_name", "draft", "citations"}
    structured output into (draft_text, chosen_image_name_or_None,
    citations). Falls back to (raw, None, []) if the response isn't valid
    JSON, so a malformed response never breaks the screen. Callers should
    run the citations through `_filter_verified_citations` before showing
    them — the model self-reports these, so they aren't guaranteed accurate
    yet."""
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return raw.strip(), None, []
    if not isinstance(payload, dict):
        return raw.strip(), None, []

    draft = str(payload.get("draft", raw)).strip()

    image_name = payload.get("image_name")
    if not image_name or image_name == _NO_IMAGE:
        image_name = None

    raw_citations = payload.get("citations", [])
    citations = [
        SourceCitation(
            source=str(c.get("source", "")).strip().lstrip("#").strip(),
            excerpt=str(c.get("excerpt", "")).strip(),
        )
        for c in raw_citations
        if isinstance(c, dict) and c.get("source") and c.get("excerpt")
    ]
    return draft, image_name, citations


_PUNCTUATION_EQUIVALENTS = str.maketrans(
    {"“": '"', "”": '"', "‘": "'", "’": "'", "–": "-", "—": "-", "…": "..."}
)

# An exact-substring check rejects a citation the moment the model reworks
# even one word while quoting (common even when explicitly told not to),
# hiding perfectly real citations. This threshold instead asks "how much of
# the excerpt is verbatim, in order, in the source?" — tolerant of small
# rewording, but a mostly-invented "quote" still won't reach it.
_MIN_CITATION_OVERLAP_RATIO = 0.85


def _normalize_for_matching(text: str) -> str:
    return " ".join(text.lower().translate(_PUNCTUATION_EQUIVALENTS).split())


def _citation_overlap_ratio(excerpt: str, context: str) -> float:
    """Fraction of `excerpt` covered by (possibly non-contiguous, in-order)
    matching runs against `context` — 1.0 for a verbatim quote, close to 0
    for one the source doesn't support at all."""
    if not excerpt:
        return 0.0
    matcher = difflib.SequenceMatcher(None, excerpt, context, autojunk=False)
    matched_chars = sum(block.size for block in matcher.get_matching_blocks())
    return matched_chars / len(excerpt)


def _filter_verified_citations(
    citations: list[SourceCitation], knowledge_context: str
) -> list[SourceCitation]:
    """Keeps only the citations whose excerpt is substantially verbatim in
    the knowledge context sent to the model. A hallucinated or largely
    invented "quote" is dropped rather than shown to staff as if it were
    reliable — better to show fewer citations than a wrong one."""
    normalized_context = _normalize_for_matching(knowledge_context)
    kept = []
    for citation in citations:
        normalized_excerpt = _normalize_for_matching(citation.excerpt)
        ratio = _citation_overlap_ratio(normalized_excerpt, normalized_context)
        if ratio >= _MIN_CITATION_OVERLAP_RATIO:
            kept.append(citation)
        else:
            logger.info(
                "simulator_citation_dropped source=%r overlap_ratio=%.2f excerpt=%r",
                citation.source,
                ratio,
                citation.excerpt,
            )
    return kept


class ProcessingService:
    def __init__(self, db: Session):
        self.db = db
        self.email_messages = EmailMessageRepository(db)
        self.email_threads = EmailThreadRepository(db)
        self.mailboxes = MailboxRepository(db)
        self.drafts = DraftRepository(db)
        self.logs = ProcessingLogRepository(db)
        self.llm_traces = LLMTraceRepository(db)
        self.prompt_service = PromptService(db)
        self.document_service = DocumentService(db)
        self.web_source_service = WebSourceService(db)
        self.agent_image_service = AgentImageService(db)
        self.knowledge_context_service = KnowledgeContextService()
        self.llm_service = LLMService()

    # --- Worker entry point ----------------------------------------------
    def process_email(self, email_message_id: int) -> None:
        email_message = self.email_messages.get(email_message_id)
        if email_message is None:
            logger.error("process_email_not_found id=%s", email_message_id)
            return

        retry_count = self.logs.count_retries_for_email(email_message_id)
        if retry_count >= settings.max_retry_attempts:
            self._log(
                mailbox_id=email_message.mailbox_id,
                email_message_id=email_message_id,
                draft_id=None,
                status=ProcessingLogStatus.IGNORED,
                step=ProcessingStep.FINALIZE,
                error_message="Max retry attempts reached; email will not be reprocessed.",
                retry_count=retry_count,
            )
            logger.warning(
                "process_email_max_retries_reached id=%s retries=%s", email_message_id, retry_count
            )
            return

        mailbox = self.mailboxes.get(email_message.mailbox_id)
        if mailbox is None:
            logger.error("process_email_mailbox_not_found email_id=%s", email_message_id)
            return

        logger.info("process_email_start id=%s subject=%r", email_message_id, email_message.subject)
        self._log(
            mailbox_id=mailbox.id,
            email_message_id=email_message_id,
            draft_id=None,
            status=ProcessingLogStatus.PROCESSING,
            step=ProcessingStep.FETCH_EMAIL,
            retry_count=retry_count,
        )

        try:
            draft = self._generate_and_store_draft(
                mailbox=mailbox, email_message=email_message, retry_count=retry_count
            )
            self._attempt_create_in_mailbox(
                mailbox=mailbox, email_message=email_message, draft=draft, retry_count=retry_count
            )

            email_message.processed_at = datetime.now(UTC)
            self.db.commit()

            self._log(
                mailbox_id=mailbox.id,
                email_message_id=email_message_id,
                draft_id=draft.id,
                status=ProcessingLogStatus.SUCCESS,
                step=ProcessingStep.FINALIZE,
                retry_count=retry_count,
            )
            logger.info("process_email_success id=%s draft_id=%s", email_message_id, draft.id)
        except Exception as exc:  # noqa: BLE001 - persisted as a processing failure, not re-raised
            new_retry_count = retry_count + 1
            status = (
                ProcessingLogStatus.RETRYING
                if new_retry_count < settings.max_retry_attempts
                else ProcessingLogStatus.FAILED
            )
            self._log(
                mailbox_id=mailbox.id,
                email_message_id=email_message_id,
                draft_id=None,
                status=status,
                step=ProcessingStep.FINALIZE,
                error_message=str(exc),
                retry_count=new_retry_count,
            )
            logger.error(
                "process_email_failed id=%s error=%s retry_count=%s",
                email_message_id,
                exc,
                new_retry_count,
            )

    # --- Simulator (no persistence) ---------------------------------------
    def simulate_draft(self, email_body: str) -> SimulateDraftResponse:
        """Generate a draft for an ad-hoc email without touching the database —
        used by the "Simulador" screen so staff can try the agent against the
        current prompt/knowledge base without a real mailbox or email."""
        prompt = self.prompt_service.get_active_prompt()
        prompt_content = prompt.content if prompt else PromptService.default_prompt_content()

        documents = self.document_service.list_active_documents()
        web_sources = self.web_source_service.list_active_web_sources()
        knowledge_context = self.knowledge_context_service.build_context(
            documents, web_sources, query=email_body
        )

        rendered_prompt = render_prompt_template(
            prompt_content,
            company_documents_context=knowledge_context,
            email_thread_context="(Prueba de simulación, sin historial previo.)",
        )
        rendered_prompt += _SOURCE_ATTRIBUTION_NOTE

        agent_images = self.agent_image_service.list_all() if settings.enable_agent_image_embedding else []
        image_schema_property, image_note = _build_agent_image_selection(agent_images)
        rendered_prompt += image_note
        response_schema = _build_simulator_schema(image_schema_property)

        llm_response = self.llm_service.generate_draft(
            system_prompt=rendered_prompt,
            user_prompt=email_body,
            trace_name="walli-draft-simulation",
            response_schema=response_schema,
        )

        generated_body, chosen_image_name, sources_used = _parse_simulator_output(llm_response.content)
        sources_used = _filter_verified_citations(sources_used, knowledge_context)
        attached_image = (
            self.agent_image_service.get_by_name(chosen_image_name) if chosen_image_name else None
        )

        return SimulateDraftResponse(
            generated_body=generated_body,
            llm_provider=llm_response.provider,
            llm_model=llm_response.model,
            sources_used=sources_used,
            attached_image_id=attached_image.id if attached_image else None,
            attached_image_name=attached_image.name if attached_image else None,
        )

    def _generate_and_store_draft(self, *, mailbox, email_message: EmailMessage, retry_count: int) -> Draft:
        prompt = self.prompt_service.get_active_prompt()
        prompt_content = prompt.content if prompt else PromptService.default_prompt_content()
        self._log(
            mailbox_id=mailbox.id,
            email_message_id=email_message.id,
            draft_id=None,
            status=ProcessingLogStatus.SUCCESS,
            step=ProcessingStep.LOAD_PROMPT,
            retry_count=retry_count,
        )

        documents = self.document_service.list_active_documents()
        web_sources = self.web_source_service.list_active_web_sources()
        self._log(
            mailbox_id=mailbox.id,
            email_message_id=email_message.id,
            draft_id=None,
            status=ProcessingLogStatus.SUCCESS,
            step=ProcessingStep.LOAD_DOCUMENTS,
            retry_count=retry_count,
        )

        knowledge_context = self.knowledge_context_service.build_context(
            documents, web_sources, query=email_message.body_text
        )
        thread_context = self._build_thread_context(email_message)
        self._log(
            mailbox_id=mailbox.id,
            email_message_id=email_message.id,
            draft_id=None,
            status=ProcessingLogStatus.SUCCESS,
            step=ProcessingStep.BUILD_CONTEXT,
            retry_count=retry_count,
        )

        email_body = email_message.body_text or email_message.body_html or "(Correo sin contenido de texto.)"
        rendered_prompt = render_prompt_template(
            prompt_content,
            company_documents_context=knowledge_context,
            email_thread_context=thread_context,
        )

        response_schema = None
        if settings.enable_agent_image_embedding:
            agent_images = self.agent_image_service.list_all()
            image_schema_property, image_note = _build_agent_image_selection(agent_images)
            rendered_prompt += image_note
            response_schema = _build_draft_schema(image_schema_property)

        try:
            llm_response = self.llm_service.generate_draft(
                system_prompt=rendered_prompt,
                user_prompt=email_body,
                trace_name=f"walli-draft-email-{email_message.id}",
                response_schema=response_schema,
            )
        except LLMProviderError:
            self._log(
                mailbox_id=mailbox.id,
                email_message_id=email_message.id,
                draft_id=None,
                status=ProcessingLogStatus.FAILED,
                step=ProcessingStep.CALL_LLM,
                error_message="LLM call failed.",
                retry_count=retry_count,
            )
            raise

        self._log(
            mailbox_id=mailbox.id,
            email_message_id=email_message.id,
            draft_id=None,
            status=ProcessingLogStatus.SUCCESS,
            step=ProcessingStep.CALL_LLM,
            retry_count=retry_count,
        )

        generated_body = llm_response.content
        attached_image = None
        if response_schema is not None:
            generated_body, chosen_image_name = _parse_draft_with_image(llm_response.content)
            if chosen_image_name:
                attached_image = self.agent_image_service.get_by_name(chosen_image_name)
                if attached_image is None:
                    logger.warning(
                        "agent_image_chosen_but_not_found email_id=%s name=%r",
                        email_message.id,
                        chosen_image_name,
                    )

        draft = Draft(
            mailbox_id=mailbox.id,
            email_message_id=email_message.id,
            prompt_template_id=prompt.id if prompt else None,
            agent_image_id=attached_image.id if attached_image else None,
            generated_body=generated_body,
            rendered_prompt=rendered_prompt,
            llm_provider=llm_response.provider,
            llm_model=llm_response.model,
            input_tokens=llm_response.input_tokens,
            output_tokens=llm_response.output_tokens,
            estimated_cost=llm_response.estimated_cost,
            status=DraftStatus.GENERATED,
        )
        self.drafts.add(draft)
        self.drafts.commit()

        total_tokens = None
        if llm_response.input_tokens is not None and llm_response.output_tokens is not None:
            total_tokens = llm_response.input_tokens + llm_response.output_tokens

        trace = LLMTrace(
            draft_id=draft.id,
            provider=llm_response.provider,
            model=llm_response.model,
            prompt_tokens=llm_response.input_tokens,
            completion_tokens=llm_response.output_tokens,
            total_tokens=total_tokens,
            estimated_cost=llm_response.estimated_cost,
            latency_ms=llm_response.latency_ms,
            langfuse_trace_id=llm_response.langfuse_trace_id,
        )
        self.llm_traces.add(trace)
        self.llm_traces.commit()

        return draft

    def _attempt_create_in_mailbox(
        self, *, mailbox, email_message: EmailMessage, draft: Draft, retry_count: int
    ) -> None:
        try:
            password = decrypt_value(mailbox.encrypted_imap_password)
            provider = build_email_provider(mailbox, password)
            previous_messages = self._list_previous_thread_messages(email_message)
            references_chain = [m.external_message_id for m in previous_messages] + [
                email_message.external_message_id
            ]
            in_reply_to = FetchedEmail(
                imap_uid=email_message.imap_uid,
                external_message_id=email_message.external_message_id,
                external_thread_id=None,
                sender=email_message.sender,
                recipients=email_message.recipients,
                subject=email_message.subject,
                body_text=email_message.body_text,
                body_html=email_message.body_html,
                received_at=email_message.received_at,
                references_chain=references_chain,
            )
            result = provider.create_draft(
                subject=email_message.subject,
                body=draft.generated_body,
                in_reply_to=in_reply_to,
                inline_image=self._load_inline_image(draft),
            )

            if result.success:
                draft.status = DraftStatus.CREATED_IN_MAILBOX
                draft.created_in_mailbox = True
                draft.mailbox_draft_id = result.mailbox_draft_id
                log_status = ProcessingLogStatus.SUCCESS
                error_message = None
            else:
                draft.status = DraftStatus.FAILED_TO_CREATE_IN_MAILBOX
                log_status = ProcessingLogStatus.FAILED
                error_message = result.message

            self.drafts.commit()
            self._log(
                mailbox_id=mailbox.id,
                email_message_id=email_message.id,
                draft_id=draft.id,
                status=log_status,
                step=ProcessingStep.CREATE_DRAFT,
                error_message=error_message,
                retry_count=retry_count,
            )
        except Exception as exc:  # noqa: BLE001 - draft creation failure is not fatal to the pipeline
            draft.status = DraftStatus.FAILED_TO_CREATE_IN_MAILBOX
            self.drafts.commit()
            self._log(
                mailbox_id=mailbox.id,
                email_message_id=email_message.id,
                draft_id=draft.id,
                status=ProcessingLogStatus.FAILED,
                step=ProcessingStep.CREATE_DRAFT,
                error_message=str(exc),
                retry_count=retry_count,
            )
            logger.error("create_draft_in_mailbox_failed email_id=%s error=%s", email_message.id, exc)

    def _load_inline_image(self, draft: Draft) -> InlineImage | None:
        if draft.agent_image_id is None:
            return None
        image = self.agent_image_service.get(draft.agent_image_id)
        if image is None:
            # Staff deleted the image between generation and this point —
            # degrade gracefully to no image rather than failing the draft.
            logger.warning(
                "agent_image_missing_at_send_time draft_id=%s agent_image_id=%s",
                draft.id,
                draft.agent_image_id,
            )
            return None
        return InlineImage(
            content=self.agent_image_service.read_bytes(image),
            content_type=image.content_type,
            filename=image.original_filename,
        )

    def _list_previous_thread_messages(self, email_message: EmailMessage) -> list[EmailMessage]:
        if email_message.thread_id is None:
            return []
        return self.email_messages.list_thread_messages(
            email_message.thread_id, exclude_message_id=email_message.id
        )

    def _build_thread_context(self, email_message: EmailMessage) -> str:
        previous_messages = self._list_previous_thread_messages(email_message)
        if not previous_messages:
            return "(Sin historial previo en este hilo.)"
        return "\n\n---\n\n".join(
            f"De: {m.sender}\nFecha: {m.received_at.isoformat()}\n\n" f"{m.body_text or m.body_html or ''}"
            for m in previous_messages
        )

    def _log(
        self,
        *,
        mailbox_id: int,
        email_message_id: int | None,
        draft_id: int | None,
        status: ProcessingLogStatus,
        step: ProcessingStep,
        retry_count: int,
        error_message: str | None = None,
    ) -> ProcessingLog:
        log = ProcessingLog(
            mailbox_id=mailbox_id,
            email_message_id=email_message_id,
            draft_id=draft_id,
            status=status,
            step=step,
            error_message=error_message,
            retry_count=retry_count,
            finished_at=datetime.now(UTC),
        )
        self.logs.add(log)
        self.logs.commit()
        return log

    # --- Read models for the API -----------------------------------------
    def _derive_overall_status(
        self, draft: Draft | None, latest_log: ProcessingLog | None
    ) -> ProcessingStatus:
        if draft is not None:
            if draft.status == DraftStatus.CREATED_IN_MAILBOX:
                return ProcessingStatus.DRAFT_CREATED_IN_MAILBOX
            if draft.status in (DraftStatus.GENERATED, DraftStatus.FAILED_TO_CREATE_IN_MAILBOX):
                return ProcessingStatus.DRAFT_GENERATED
            if draft.status == DraftStatus.DISCARDED:
                return ProcessingStatus.IGNORED

        if latest_log is None:
            return ProcessingStatus.RECEIVED
        if latest_log.status == ProcessingLogStatus.FAILED:
            return ProcessingStatus.FAILED
        if latest_log.status == ProcessingLogStatus.IGNORED:
            return ProcessingStatus.IGNORED
        if latest_log.status in (ProcessingLogStatus.PROCESSING, ProcessingLogStatus.RETRYING):
            return ProcessingStatus.PROCESSING
        return ProcessingStatus.RECEIVED

    def list_processing(self, limit: int = 100, offset: int = 0) -> list[ProcessingListItem]:
        messages = self.email_messages.list(limit=limit, offset=offset)
        items: list[ProcessingListItem] = []
        for message in messages:
            draft = self.drafts.get_by_email_message_id(message.id)
            latest_log = self.logs.latest_for_email(message.id)
            mailbox = self.mailboxes.get(message.mailbox_id)
            items.append(
                ProcessingListItem(
                    email_message_id=message.id,
                    mailbox_id=message.mailbox_id,
                    mailbox_name=mailbox.name if mailbox else "",
                    subject=message.subject,
                    sender=message.sender,
                    received_at=message.received_at,
                    status=self._derive_overall_status(draft, latest_log),
                    draft_id=draft.id if draft else None,
                    error_message=latest_log.error_message if latest_log else None,
                )
            )
        return items

    def get_processing_detail(self, email_message_id: int) -> ProcessingDetail | None:
        message = self.email_messages.get(email_message_id)
        if message is None:
            return None

        draft = self.drafts.get_by_email_message_id(email_message_id)
        logs = self.logs.list_for_email(email_message_id)
        latest_log = logs[-1] if logs else None
        retry_count = latest_log.retry_count if latest_log else 0

        documents_used: list[str] = []
        web_sources_used: list[str] = []
        # The prompt actually sent to the LLM (placeholders already substituted
        # with the real knowledge context/email/thread at generation time), not
        # the raw template, so this reflects exactly what the model saw.
        prompt_content_snapshot = draft.rendered_prompt if draft else None
        if draft:
            active_documents = self.document_service.list_active_documents()
            documents_used = [d.original_filename for d in active_documents]
            active_web_sources = self.web_source_service.list_active_web_sources()
            web_sources_used = [w.name for w in active_web_sources]

        return ProcessingDetail(
            email_message_id=message.id,
            mailbox_id=message.mailbox_id,
            subject=message.subject,
            sender=message.sender,
            recipients=message.recipients,
            body_text=message.body_text,
            body_html=message.body_html,
            received_at=message.received_at,
            prompt_template_id=draft.prompt_template_id if draft else None,
            prompt_content_snapshot=prompt_content_snapshot,
            documents_used=documents_used,
            web_sources_used=web_sources_used,
            thread_context=self._build_thread_context(message),
            generated_body=draft.generated_body if draft else None,
            draft_id=draft.id if draft else None,
            draft_status=draft.status.value if draft else None,
            final_status=self._derive_overall_status(draft, latest_log),
            retry_count=retry_count,
            logs=list(logs),
        )
