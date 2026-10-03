"""DriveSource CRUD and the content-hash sync cycle. `sync()` is the single
entry point both the manual "sync now" endpoint and the Celery Beat task
call — mirrors how WebSourceService.refresh used to work, but by content
hash, not by crawling.
"""

import hashlib
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.drive_source import DriveSource
from app.repositories.drive_source_repository import DriveSourceRepository
from app.services.drive_sync import DriveDownloadError, download_drive_file
from app.services.openai_file_service import (
    FileTooLargeError,
    UnsupportedFileTypeError,
    delete_file,
    get_openai_client,
    upload_bytes,
)

logger = get_logger(__name__)


class DriveSourceService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = DriveSourceRepository(db)

    def list_drive_sources(self) -> list[DriveSource]:
        return self.repo.list(limit=500)

    def list_active_drive_sources(self) -> list[DriveSource]:
        return self.repo.list_active()

    def get(self, drive_source_id: int) -> DriveSource | None:
        return self.repo.get(drive_source_id)

    def create(self, *, name: str, drive_url: str, is_active: bool = True) -> DriveSource:
        drive_source = DriveSource(name=name, drive_url=drive_url, is_active=is_active)
        self.repo.add(drive_source)
        self.repo.commit()
        logger.info("drive_source_created id=%s drive_url=%s", drive_source.id, drive_url)
        return self.sync(drive_source)  # synchronous initial sync for immediate feedback

    def update(self, drive_source: DriveSource, **fields) -> DriveSource:
        for key, value in fields.items():
            if value is not None:
                setattr(drive_source, key, value)
        self.repo.commit()
        self.repo.refresh(drive_source)
        return drive_source

    def delete(self, drive_source: DriveSource) -> None:
        if drive_source.openai_file_id:
            delete_file(client=get_openai_client(), file_id=drive_source.openai_file_id)
        self.repo.delete(drive_source)
        self.repo.commit()

    def set_active(self, drive_source: DriveSource, is_active: bool) -> DriveSource:
        drive_source.is_active = is_active
        self.repo.commit()
        self.repo.refresh(drive_source)
        return drive_source

    def sync(self, drive_source: DriveSource) -> DriveSource:
        """Never raises: failures are stored on `last_sync_error` instead,
        since this also runs unattended from Celery Beat."""
        try:
            downloaded = download_drive_file(drive_source.drive_url)
        except DriveDownloadError as exc:
            drive_source.last_sync_error = str(exc)
            drive_source.last_checked_at = datetime.now(UTC)
            self.repo.commit()
            self.repo.refresh(drive_source)
            logger.warning("drive_source_sync_failed id=%s error=%s", drive_source.id, exc)
            return drive_source

        new_hash = hashlib.sha256(downloaded.content).hexdigest()
        drive_source.last_checked_at = datetime.now(UTC)

        if new_hash == drive_source.content_hash and drive_source.openai_file_id:
            # Unchanged content and we already have a live OpenAI file — no-op.
            drive_source.last_sync_error = None
            self.repo.commit()
            self.repo.refresh(drive_source)
            return drive_source

        try:
            client = get_openai_client()
            result = upload_bytes(client=client, filename=downloaded.filename, content=downloaded.content)
        except (FileTooLargeError, UnsupportedFileTypeError) as exc:
            drive_source.last_sync_error = str(exc)
            self.repo.commit()
            self.repo.refresh(drive_source)
            logger.warning("drive_source_upload_rejected id=%s error=%s", drive_source.id, exc)
            return drive_source
        except Exception as exc:  # noqa: BLE001
            drive_source.last_sync_error = f"Error al subir el archivo a OpenAI: {exc}"
            self.repo.commit()
            self.repo.refresh(drive_source)
            logger.error("drive_source_openai_upload_failed id=%s error=%s", drive_source.id, exc)
            return drive_source

        stale_file_id = drive_source.openai_file_id
        drive_source.openai_file_id = result.file_id
        drive_source.openai_file_uploaded_at = datetime.now(UTC)
        drive_source.content_hash = new_hash
        drive_source.size_bytes = len(downloaded.content)
        drive_source.last_sync_error = None
        self.repo.commit()
        self.repo.refresh(drive_source)

        if stale_file_id:
            delete_file(client=get_openai_client(), file_id=stale_file_id)  # best-effort, after commit

        logger.info("drive_source_synced id=%s openai_file_id=%s", drive_source.id, result.file_id)
        return drive_source
