"""Shared enums used across ORM models, schemas and services."""

import enum


class UserRole(enum.StrEnum):
    ADMIN = "admin"
    AGENT = "agent"


class MailboxProvider(enum.StrEnum):
    NOMINALIA = "nominalia"
    GENERIC_IMAP = "generic_imap"


class EmailThreadStatus(enum.StrEnum):
    OPEN = "open"
    AWAITING_REVIEW = "awaiting_review"
    CLOSED = "closed"


class ProcessingStatus(enum.StrEnum):
    RECEIVED = "received"
    PROCESSING = "processing"
    DRAFT_GENERATED = "draft_generated"
    DRAFT_CREATED_IN_MAILBOX = "draft_created_in_mailbox"
    FAILED = "failed"
    IGNORED = "ignored"


class ProcessingLogStatus(enum.StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"
    RETRYING = "retrying"
    IGNORED = "ignored"


class ProcessingStep(enum.StrEnum):
    FETCH_EMAIL = "fetch_email"
    LOAD_PROMPT = "load_prompt"
    LOAD_DOCUMENTS = "load_documents"
    BUILD_CONTEXT = "build_context"
    CALL_LLM = "call_llm"
    CREATE_DRAFT = "create_draft"
    FINALIZE = "finalize"


class DraftStatus(enum.StrEnum):
    GENERATED = "generated"
    CREATED_IN_MAILBOX = "created_in_mailbox"
    FAILED_TO_CREATE_IN_MAILBOX = "failed_to_create_in_mailbox"
    DISCARDED = "discarded"
