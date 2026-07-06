from app.services.web_crawler import CrawlResult
from app.services.web_source_service import WebSourceService


def test_create_triggers_synchronous_initial_refresh(db_session, monkeypatch):
    monkeypatch.setattr(
        "app.services.web_source_service.crawl_site",
        lambda root_url, max_pages: CrawlResult(
            pages_crawled=3, extracted_text="Contenido rastreado.", error=None
        ),
    )

    service = WebSourceService(db_session)
    web_source = service.create(name="laWALL web", root_url="https://la-wall.com/", max_pages=10)

    assert web_source.pages_crawled == 3
    assert web_source.extracted_text == "Contenido rastreado."
    assert web_source.last_fetched_at is not None
    assert web_source.last_fetch_error is None


def test_refresh_stores_error_without_raising(db_session, monkeypatch):
    monkeypatch.setattr(
        "app.services.web_source_service.crawl_site",
        lambda root_url, max_pages: CrawlResult(
            pages_crawled=0, extracted_text="", error="No se pudo conectar."
        ),
    )

    service = WebSourceService(db_session)
    web_source = service.create(name="Sitio caído", root_url="https://caido.example/", max_pages=5)

    assert web_source.pages_crawled == 0
    assert web_source.extracted_text is None
    assert web_source.last_fetch_error == "No se pudo conectar."


def test_list_active_web_sources_excludes_inactive(db_session, monkeypatch):
    monkeypatch.setattr(
        "app.services.web_source_service.crawl_site",
        lambda root_url, max_pages: CrawlResult(pages_crawled=1, extracted_text="Ok", error=None),
    )

    service = WebSourceService(db_session)
    active = service.create(name="Activa", root_url="https://activa.example/", max_pages=5)
    inactive = service.create(name="Inactiva", root_url="https://inactiva.example/", max_pages=5)
    service.set_active(inactive, False)

    active_sources = service.list_active_web_sources()
    assert active.id in [w.id for w in active_sources]
    assert inactive.id not in [w.id for w in active_sources]
