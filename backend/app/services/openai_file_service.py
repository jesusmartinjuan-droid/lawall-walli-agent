"""Thin wrapper around OpenAI's Files API: upload bytes, delete a stale file
best-effort, validate size/type before ever calling OpenAI. Isolated here so
DocumentService and DriveSourceService share identical upload/validation/
error-handling behavior and both stay easily mockable in tests.
"""

from dataclasses import dataclass

from app.core.config import settings
from app.core.logging import get_logger
from app.core.supported_file_types import SUPPORTED_FILE_EXTENSIONS, is_supported_file_type

logger = get_logger(__name__)


class FileTooLargeError(Exception):
    pass


class UnsupportedFileTypeError(Exception):
    pass


@dataclass
class OpenAIFileUploadResult:
    file_id: str


def validate_upload_size(size_bytes: int) -> None:
    if size_bytes > settings.max_upload_file_bytes:
        max_mb = settings.max_upload_file_bytes // (1024 * 1024)
        raise FileTooLargeError(f"El archivo supera el tamaño máximo permitido ({max_mb}MB).")


def validate_file_type(filename: str) -> None:
    if not is_supported_file_type(filename):
        allowed = ", ".join(sorted(SUPPORTED_FILE_EXTENSIONS))
        raise UnsupportedFileTypeError(
            f"'{filename}' no es un tipo de archivo que el agente pueda leer. Tipos admitidos: {allowed}"
        )


def upload_bytes(*, client, filename: str, content: bytes) -> OpenAIFileUploadResult:
    """`client` is an already-constructed `openai.OpenAI` instance — callers
    own client construction so this stays easily mockable in tests."""
    validate_file_type(filename)
    validate_upload_size(len(content))
    file_obj = client.files.create(file=(filename, content), purpose="assistants")
    return OpenAIFileUploadResult(file_id=file_obj.id)


def delete_file(*, client, file_id: str | None) -> None:
    """Best-effort: a delete failure (already gone, network error, etc.)
    must never block a re-upload — log and move on."""
    if not file_id:
        return
    try:
        client.files.delete(file_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("openai_file_delete_failed file_id=%s error=%s", file_id, exc)


def get_openai_client():
    from openai import OpenAI

    return OpenAI(api_key=settings.openai_api_key)
