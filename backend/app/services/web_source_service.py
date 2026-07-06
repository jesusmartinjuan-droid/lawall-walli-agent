"""WebSource CRUD and the crawl/refresh cycle.

`refresh()` is the single entry point both the manual "refresh now" endpoint
and the periodic Celery Beat task call, mirroring how MailboxService.poll_mailbox
is the shared fetch method for a periodically-polled external source.
"""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.web_source import WebSource
from app.repositories.web_source_repository import WebSourceRepository
from app.services.web_crawler import crawl_site

logger = get_logger(__name__)


class WebSourceService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = WebSourceRepository(db)

    def list_web_sources(self) -> list[WebSource]:
        return self.repo.list(limit=500)

    def list_active_web_sources(self) -> list[WebSource]:
        return self.repo.list_active()

    def get(self, web_source_id: int) -> WebSource | None:
        return self.repo.get(web_source_id)

    def create(self, *, name: str, root_url: str, max_pages: int, is_active: bool = True) -> WebSource:
        web_source = WebSource(name=name, root_url=root_url, max_pages=max_pages, is_active=is_active)
        self.repo.add(web_source)
        self.repo.commit()
        logger.info("web_source_created id=%s root_url=%s", web_source.id, root_url)
        # Synchronous initial crawl for immediate feedback that the URL works.
        return self.refresh(web_source)

    def update(self, web_source: WebSource, **fields) -> WebSource:
        for key, value in fields.items():
            if value is not None:
                setattr(web_source, key, value)
        self.repo.commit()
        self.repo.refresh(web_source)
        return web_source

    def delete(self, web_source: WebSource) -> None:
        self.repo.delete(web_source)
        self.repo.commit()

    def set_active(self, web_source: WebSource, is_active: bool) -> WebSource:
        web_source.is_active = is_active
        self.repo.commit()
        self.repo.refresh(web_source)
        logger.info("web_source_active_flag_changed id=%s is_active=%s", web_source.id, is_active)
        return web_source

    def refresh(self, web_source: WebSource) -> WebSource:
        """Crawl `web_source.root_url` and persist the result. Never raises:
        failures are stored on `last_fetch_error` instead, since this is also
        called unattended from the Celery Beat task."""
        result = crawl_site(web_source.root_url, web_source.max_pages)

        web_source.extracted_text = result.extracted_text or None
        web_source.pages_crawled = result.pages_crawled
        web_source.last_fetched_at = datetime.now(UTC)
        web_source.last_fetch_error = result.error

        self.repo.commit()
        self.repo.refresh(web_source)
        logger.info(
            "web_source_refreshed id=%s pages_crawled=%s error=%s",
            web_source.id,
            result.pages_crawled,
            result.error,
        )
        return web_source
