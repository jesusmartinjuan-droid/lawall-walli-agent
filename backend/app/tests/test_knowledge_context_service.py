from app.models.document import Document
from app.models.web_source import WebSource
from app.services.knowledge_context_service import KnowledgeContextService


def _document(text: str, filename: str = "doc.txt") -> Document:
    return Document(
        filename=filename,
        original_filename=filename,
        content_type="text/plain",
        storage_path="/tmp/doc.txt",
        extracted_text=text,
        is_active=True,
    )


def _web_source(text: str | None, name: str = "Sitio web") -> WebSource:
    return WebSource(
        name=name,
        root_url="https://example.com/",
        max_pages=10,
        is_active=True,
        extracted_text=text,
    )


def test_build_context_with_no_documents_returns_placeholder():
    service = KnowledgeContextService(max_chars=1000)
    assert "No hay documentos" in service.build_context([])


def test_build_context_concatenates_active_documents():
    service = KnowledgeContextService(max_chars=1000)
    docs = [
        _document("Horario: 9 a 18h", "horario.txt"),
        _document("Tarifas: consultar web", "tarifas.txt"),
    ]
    context = service.build_context(docs)
    assert "horario.txt" in context
    assert "Horario: 9 a 18h" in context
    assert "tarifas.txt" in context


def test_build_context_respects_max_chars_budget():
    service = KnowledgeContextService(max_chars=10)
    docs = [_document("A" * 100, "big.txt")]
    context = service.build_context(docs)
    assert len(context) < 100


def test_build_context_includes_documents_and_web_sources():
    service = KnowledgeContextService(max_chars=1000)
    docs = [_document("Horario: 9 a 18h", "horario.txt")]
    web_sources = [_web_source("Precios y servicios de la empresa.", "laWALL web")]
    context = service.build_context(docs, web_sources)
    assert "horario.txt" in context
    assert "laWALL web" in context
    assert "Precios y servicios" in context


def test_build_context_shares_budget_between_documents_and_web_sources():
    service = KnowledgeContextService(max_chars=15)
    docs = [_document("A" * 100, "big.txt")]
    web_sources = [_web_source("B" * 100, "big-site")]
    context = service.build_context(docs, web_sources)
    assert "big-site" not in context


def test_build_context_only_web_sources_no_documents():
    service = KnowledgeContextService(max_chars=1000)
    web_sources = [_web_source("Contenido del sitio web.", "laWALL web")]
    context = service.build_context([], web_sources)
    assert "laWALL web" in context
    assert "Contenido del sitio web." in context


def test_build_context_skips_web_source_without_extracted_text():
    service = KnowledgeContextService(max_chars=1000)
    web_sources = [_web_source(None, "sin-contenido")]
    context = service.build_context([], web_sources)
    assert "sin-contenido" not in context
    assert "No hay documentos" in context
