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

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.encryption import decrypt_value
from app.core.logging import get_logger
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
from app.schemas.processing import ProcessingDetail, ProcessingListItem
from app.services.document_service import DocumentService
from app.services.email_provider_service import FetchedEmail
from app.services.knowledge_context_service import KnowledgeContextService
from app.services.llm_service import LLMProviderError, LLMService
from app.services.mailbox_service import build_email_provider
from app.services.prompt_service import PromptService
from app.services.web_source_service import WebSourceService

logger = get_logger(__name__)


def render_prompt_template(
    template: str, *, company_documents_context: str, email_body: str, email_thread_context: str
) -> str:
    return (
        template.replace("{{company_documents_context}}", company_documents_context)
        .replace("{{email_body}}", email_body)
        .replace("{{email_thread_context}}", email_thread_context)
    )


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
            email_body=email_body,
            email_thread_context=thread_context,
        )

        try:
            llm_response = self.llm_service.generate_draft(
                system_prompt=rendered_prompt,
                user_prompt=email_body,
                trace_name=f"walli-draft-email-{email_message.id}",
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

        draft = Draft(
            mailbox_id=mailbox.id,
            email_message_id=email_message.id,
            prompt_template_id=prompt.id if prompt else None,
            generated_body=llm_response.content,
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
                subject=email_message.subject, body=draft.generated_body, in_reply_to=in_reply_to
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
