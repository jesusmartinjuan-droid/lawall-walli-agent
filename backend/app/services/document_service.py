"""Local file upload + OpenAI Files API sync for "Archivos locales del
agente". No text extraction — the real bytes are stored locally (for
debugging/re-upload) and uploaded as-is to OpenAI's Files API;
`Document.openai_file_id` is what actually gets attached to a generation
call (see LLMService / ProcessingService)."""

import os
import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.models.document import Document
from app.repositories.document_repository import DocumentRepository
from app.services.openai_file_service import (
    delete_file,
    get_openai_client,
    upload_bytes,
    validate_file_type,
    validate_upload_size,
)

logger = get_logger(__name__)


class DocumentService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = DocumentRepository(db)

    def list_documents(self) -> list[Document]:
        return self.repo.list(limit=500)

    def list_active_documents(self) -> list[Document]:
        return self.repo.list_active()

    def get(self, document_id: int) -> Document | None:
        return self.repo.get(document_id)

    def upload(self, *, original_filename: str, content_type: str, file_bytes: bytes) -> Document:
        # Validate before touching disk — a rejected file shouldn't leave a
        # half-written artifact behind.
        validate_file_type(original_filename)
        validate_upload_size(len(file_bytes))

        os.makedirs(settings.documents_storage_path, exist_ok=True)
        extension = os.path.splitext(original_filename)[1]
        stored_filename = f"{uuid.uuid4().hex}{extension}"
        storage_path = os.path.join(settings.documents_storage_path, stored_filename)
        with open(storage_path, "wb") as fh:
            fh.write(file_bytes)

        document = Document(
            filename=stored_filename,
            original_filename=original_filename,
            content_type=content_type,
            storage_path=storage_path,
            size_bytes=len(file_bytes),
            is_active=True,
        )
        self.repo.add(document)
        self.repo.commit()

        self._sync_to_openai(document, file_bytes)
        logger.info("document_uploaded id=%s filename=%s", document.id, original_filename)
        return document

    def _sync_to_openai(self, document: Document, file_bytes: bytes) -> None:
        try:
            client = get_openai_client()
            result = upload_bytes(client=client, filename=document.original_filename, content=file_bytes)
            document.openai_file_id = result.file_id
            document.openai_file_uploaded_at = datetime.now(UTC)
            document.openai_upload_error = None
        except Exception as exc:  # noqa: BLE001 - never block the upload record itself
            logger.error("document_openai_upload_failed id=%s error=%s", document.id, exc)
            document.openai_upload_error = str(exc)
        self.repo.commit()

    def delete(self, document_id: int) -> bool:
        document = self.repo.get(document_id)
        if not document:
            return False
        if document.openai_file_id:
            delete_file(client=get_openai_client(), file_id=document.openai_file_id)
        if os.path.exists(document.storage_path):
            try:
                os.remove(document.storage_path)
            except OSError as exc:
                logger.warning("document_file_delete_failed path=%s error=%s", document.storage_path, exc)
        self.repo.delete(document)
        self.repo.commit()
        logger.info("document_deleted id=%s", document_id)
        return True
