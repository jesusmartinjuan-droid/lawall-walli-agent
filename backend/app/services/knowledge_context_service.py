"""Builds the "company knowledge" block injected into the LLM prompt.

Phase 1 (current): concatenate the extracted text of all active documents
and active web sources, truncated to a configurable character budget. No
ranking, no retrieval.

Phase 2 (future): this is the seam where RAG gets added — replace
`build_context` with a call to a vector search that ranks/selects the most
relevant chunks for the given email instead of naively concatenating
everything. Callers (`ProcessingService`) don't need to change: they only
depend on `build_context(documents, web_sources, query) -> str`.
"""

from app.core.config import settings
from app.core.logging import get_logger
from app.models.document import Document
from app.models.web_source import WebSource

logger = get_logger(__name__)


class KnowledgeContextService:
    def __init__(self, max_chars: int | None = None):
        self.max_chars = max_chars or settings.max_knowledge_context_chars

    def build_context(
        self,
        documents: list[Document],
        web_sources: list[WebSource] | None = None,
        query: str | None = None,
    ) -> str:
        """`query` (the email being answered) is accepted but unused in phase 1;
        it is here so the phase-2 RAG implementation is a drop-in replacement."""
        del query
        web_sources = web_sources or []

        # Documents and web sources share a single character budget: unify
        # them into one (label, text) list, documents first, before the
        # truncation loop below.
        sources: list[tuple[str, str]] = [
            (document.original_filename, (document.extracted_text or "").strip()) for document in documents
        ] + [(web_source.name, (web_source.extracted_text or "").strip()) for web_source in web_sources]

        empty_message = "(No hay documentos ni sitios web de conocimiento cargados.)"
        if not sources:
            return empty_message

        total_available_chars = sum(len(text) for _label, text in sources)
        if total_available_chars > self.max_chars:
            logger.warning(
                "knowledge_context_truncated available_chars=%s max_chars=%s",
                total_available_chars,
                self.max_chars,
            )

        sections: list[str] = []
        remaining = self.max_chars
        for label, text in sources:
            if remaining <= 0:
                break
            if not text:
                continue
            chunk = text[:remaining]
            sections.append(f"### {label}\n{chunk}")
            remaining -= len(chunk)

        return "\n\n".join(sections) if sections else empty_message
