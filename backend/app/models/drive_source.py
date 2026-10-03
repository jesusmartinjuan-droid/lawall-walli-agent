from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class DriveSource(Base, TimestampMixin):
    """A single file staff shared from Google Drive as "anyone with the
    link", synced by content hash (not Drive API modifiedTime — Walli has no
    real Drive API access, see drive_sync.py). Walli downloads the real
    bytes periodically and re-uploads to OpenAI only when the hash changes."""

    __tablename__ = "drive_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    drive_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    openai_file_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    openai_file_uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<DriveSource id={self.id} drive_url={self.drive_url!r}>"
