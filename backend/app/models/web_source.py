from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class WebSource(Base, TimestampMixin):
    """A company website (or specific page) periodically crawled for text to
    feed into the LLM knowledge context, alongside uploaded Documents.

    `extracted_text` holds the concatenated visible text of every page
    visited during the last successful crawl (see app/services/web_crawler.py).
    """

    __tablename__ = "web_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    root_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    max_pages: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    pages_crawled: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_fetch_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<WebSource id={self.id} root_url={self.root_url!r}>"
