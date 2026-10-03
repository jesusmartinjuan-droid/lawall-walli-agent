"""Downloads the real bytes of a single Google-Drive-shared file.

No crawling, no BFS. Four URL shapes are detected, each with the matching
download/export strategy:
  - drive.google.com/file/d/{id}/...         -> direct binary download
  - docs.google.com/document/d/{id}/...      -> export as .docx
  - docs.google.com/spreadsheets/d/{id}/...  -> export as .xlsx
  - docs.google.com/presentation/d/{id}/...  -> export as .pptx

Exporting native Google Docs/Sheets/Slides as real office formats (instead
of the old plain-text export) preserves tables — the exact thing the old
text-extraction pipeline used to destroy.
"""

import re
from dataclasses import dataclass

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)

REQUEST_TIMEOUT_SECONDS = 30.0

_DRIVE_FILE_PATTERN = re.compile(r"drive\.google\.com/file/d/([a-zA-Z0-9_-]+)")
_DOCS_PATTERN = re.compile(r"docs\.google\.com/document/d/([a-zA-Z0-9_-]+)")
_SHEETS_PATTERN = re.compile(r"docs\.google\.com/spreadsheets/d/([a-zA-Z0-9_-]+)")
_SLIDES_PATTERN = re.compile(r"docs\.google\.com/presentation/d/([a-zA-Z0-9_-]+)")

_EXPORT_FORMATS = {
    "document": "docx",
    "spreadsheets": "xlsx",
    "presentation": "pptx",
}


class DriveDownloadError(Exception):
    """Carries a user-facing Spanish message; never leaks raw exception text."""


@dataclass
class DownloadedDriveFile:
    content: bytes
    filename: str
    content_type: str


def detect_drive_file_id(url: str) -> tuple[str, str] | None:
    """Returns (kind, file_id) where kind is one of "binary", "document",
    "spreadsheets", "presentation", or None if the URL doesn't match any
    known Drive/Docs/Sheets/Slides pattern."""
    for pattern, kind in (
        (_DRIVE_FILE_PATTERN, "binary"),
        (_DOCS_PATTERN, "document"),
        (_SHEETS_PATTERN, "spreadsheets"),
        (_SLIDES_PATTERN, "presentation"),
    ):
        match = pattern.search(url)
        if match:
            return kind, match.group(1)
    return None


def download_drive_file(drive_url: str, *, client: httpx.Client | None = None) -> DownloadedDriveFile:
    """Never raises anything except DriveDownloadError with a Spanish,
    user-facing message — this is called both from the manual "add/sync"
    endpoint and unattended from Celery Beat."""
    detected = detect_drive_file_id(drive_url)
    if detected is None:
        raise DriveDownloadError(
            "Ese enlace no es un documento de Drive reconocido. Pega un enlace a un archivo "
            "(drive.google.com/file/d/...), un Google Doc, una Hoja de cálculo o una Presentación."
        )
    kind, file_id = detected

    owns_client = client is None
    client = client or httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS, follow_redirects=True)
    try:
        if kind == "binary":
            return _download_binary_file(file_id, client)
        return _export_native_file(file_id, kind, client)
    finally:
        if owns_client:
            client.close()


def _download_binary_file(file_id: str, client: httpx.Client) -> DownloadedDriveFile:
    url = f"https://drive.google.com/uc?export=download&id={file_id}"
    try:
        response = client.get(url)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise DriveDownloadError(f"No se pudo descargar el archivo de Drive: {exc}") from exc

    content_type = response.headers.get("content-type", "")
    if "text/html" in content_type:
        # Either not shared publicly, or Google's >100MB virus-scan
        # confirmation page (it also returns HTML in that case) — we don't
        # attempt to parse/submit the confirmation token, just surface this
        # as a known limitation.
        raise DriveDownloadError(
            "No se pudo descargar el archivo. Comprueba que esté compartido como 'Cualquiera con "
            "el enlace puede ver'. Si el archivo pesa más de 100MB, Google requiere una "
            "confirmación manual que Walli todavía no soporta: descárgalo y súbelo como archivo "
            "local en su lugar."
        )

    filename = _filename_from_content_disposition(response.headers.get("content-disposition")) or file_id
    return DownloadedDriveFile(content=response.content, filename=filename, content_type=content_type)


def _export_native_file(file_id: str, kind: str, client: httpx.Client) -> DownloadedDriveFile:
    extension = _EXPORT_FORMATS[kind]
    export_url = f"https://docs.google.com/{kind}/d/{file_id}/export?format={extension}"
    try:
        response = client.get(export_url)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise DriveDownloadError(f"No se pudo exportar el documento de Drive: {exc}") from exc

    if "text/html" in response.headers.get("content-type", ""):
        raise DriveDownloadError(
            "El documento no es accesible. Comprueba que esté compartido como 'Cualquiera con el "
            "enlace puede ver'."
        )

    return DownloadedDriveFile(
        content=response.content,
        filename=f"{file_id}.{extension}",
        content_type=response.headers.get("content-type", ""),
    )


def _filename_from_content_disposition(header: str | None) -> str | None:
    if not header:
        return None
    match = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', header)
    return match.group(1) if match else None
