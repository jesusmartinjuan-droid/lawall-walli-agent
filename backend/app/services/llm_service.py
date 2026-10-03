"""LLM abstraction layer.

The rest of the app depends only on `LLMService` / `LLMProvider`, never on a
concrete SDK (e.g. `openai`) directly. The real provider calls OpenAI's
Responses API with `code_interpreter` (reading the active knowledge files
directly — no text extraction) and `web_search` (live web lookups) — no
structured JSON output anywhere in this pipeline anymore.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.core.config import settings
from app.core.logging import get_logger
from app.core.retry import with_retry
from app.services import langfuse_client

logger = get_logger(__name__)


@dataclass
class GeneratedImage:
    filename: str
    content_type: str
    content: bytes


@dataclass
class LLMResponse:
    content: str
    provider: str
    model: str
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: int
    estimated_cost: float | None = None
    langfuse_trace_id: str | None = None
    # The literal Python code the model actually ran via code_interpreter,
    # one entry per code_interpreter_call in response.output — scanned by
    # ProcessingService for attached filenames to derive "sources actually
    # consulted" (grounded citations), see processing_service.py.
    code_interpreter_snippets: list[str] = field(default_factory=list)
    # The query/URL of each web_search_call the model made, for the same
    # "what did it actually consult" derivation.
    web_search_queries: list[str] = field(default_factory=list)
    # Any image file the model's code_interpreter code produced or displayed
    # during this call — a freshly rendered chart, or an existing uploaded
    # image it chose to show as-is. Real bytes, downloaded from the sandbox
    # container (see `_extract_generated_images`).
    generated_images: list[GeneratedImage] = field(default_factory=list)


class LLMProviderError(Exception):
    pass


class LLMProvider(ABC):
    name: str

    @abstractmethod
    def generate(
        self, *, instructions: str, input_text: str, file_ids: list[str] | None = None
    ) -> LLMResponse: ...


class OpenAILLMProvider(LLMProvider):
    name = "openai"

    def __init__(self, api_key: str, model: str, max_tokens: int):
        self.model = model
        self.max_tokens = max_tokens
        self._api_key = api_key

    def _client(self):
        from openai import OpenAI

        return OpenAI(api_key=self._api_key)

    def generate(
        self, *, instructions: str, input_text: str, file_ids: list[str] | None = None
    ) -> LLMResponse:
        file_ids = file_ids or []

        def _call():
            client = self._client()
            tools: list[dict] = [{"type": "web_search"}]
            if file_ids:
                tools.append(
                    {"type": "code_interpreter", "container": {"type": "auto", "file_ids": file_ids}}
                )
            # No `temperature`: gpt-5.6-sol (and the rest of this reasoning-tier
            # family) rejects it outright ("Unsupported parameter") — confirmed
            # against the real API, not an assumption.
            return client.responses.create(
                model=self.model,
                max_output_tokens=self.max_tokens,
                instructions=instructions,
                input=input_text,
                tools=tools,
            )

        started = time.monotonic()
        response = with_retry(_call, exceptions=(Exception,))
        latency_ms = int((time.monotonic() - started) * 1000)

        if not response.output_text and getattr(response, "status", None) == "incomplete":
            logger.warning(
                "openai_response_incomplete model=%s reason=%s max_output_tokens=%s",
                self.model,
                getattr(getattr(response, "incomplete_details", None), "reason", None),
                self.max_tokens,
            )

        usage = response.usage
        code_snippets = [
            item.code
            for item in response.output
            if getattr(item, "type", None) == "code_interpreter_call" and item.code
        ]
        web_search_queries = [
            query
            for item in response.output
            if getattr(item, "type", None) == "web_search_call"
            and (query := _describe_web_search_action(getattr(item, "action", None)))
        ]
        container_ids = {
            item.container_id
            for item in response.output
            if getattr(item, "type", None) == "code_interpreter_call" and getattr(item, "container_id", None)
        }
        generated_images = (
            _extract_generated_images(self._client(), container_ids, file_ids) if container_ids else []
        )

        return LLMResponse(
            content=response.output_text or "",
            provider=self.name,
            model=self.model,
            input_tokens=getattr(usage, "input_tokens", None),
            output_tokens=getattr(usage, "output_tokens", None),
            latency_ms=latency_ms,
            code_interpreter_snippets=code_snippets,
            web_search_queries=web_search_queries,
            generated_images=generated_images,
        )


_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif")


def _extract_generated_images(
    client, container_ids: set[str], input_file_ids: list[str]
) -> list[GeneratedImage]:
    """Downloads any image file present in a code_interpreter sandbox
    container after the call — a chart the model rendered, or an existing
    uploaded image it chose to display as-is. Excludes the files we
    ourselves attached as input (their sandbox path embeds their original
    `file_id`, e.g. `/mnt/data/file-XXXX-tabla.png`) so only what the model
    actually produced/surfaced during this specific call is returned. Never
    raises — a download hiccup here must never break draft generation."""
    images: list[GeneratedImage] = []
    for container_id in container_ids:
        try:
            container_files = client.containers.files.list(container_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("container_files_list_failed container_id=%s error=%s", container_id, exc)
            continue

        for container_file in container_files.data:
            path = getattr(container_file, "path", "") or ""
            if not path.lower().endswith(_IMAGE_EXTENSIONS):
                continue
            if any(file_id in path for file_id in input_file_ids):
                continue

            try:
                content = client.containers.files.content.retrieve(
                    file_id=container_file.id, container_id=container_id
                ).read()
            except Exception as exc:  # noqa: BLE001
                logger.warning("container_file_download_failed file_id=%s error=%s", container_file.id, exc)
                continue

            filename = path.rsplit("/", 1)[-1]
            content_type = "image/png" if filename.lower().endswith(".png") else "image/jpeg"
            images.append(GeneratedImage(filename=filename, content_type=content_type, content=content))
    return images


def _describe_web_search_action(action) -> str | None:
    """`action` is a union of ActionSearch (.query)/ActionOpenPage (.url)/
    ActionFind (.url, .pattern) — pick whichever identifying field it has."""
    if action is None:
        return None
    return getattr(action, "query", None) or getattr(action, "url", None) or getattr(action, "pattern", None)


class MockLLMProvider(LLMProvider):
    """Deterministic fallback used when no LLM_PROVIDER API key is configured.

    Keeps local development and tests functional without real credentials.
    """

    name = "mock"

    def generate(
        self, *, instructions: str, input_text: str, file_ids: list[str] | None = None
    ) -> LLMResponse:
        started = time.monotonic()
        content = (
            "Gracias por tu mensaje. Estamos revisando tu consulta y te "
            "responderemos con la información necesaria en cuanto la tengamos "
            "disponible.\n\n[Borrador generado por el proveedor LLM 'mock': "
            "configura OPENAI_API_KEY para generar respuestas reales.]"
        )
        latency_ms = int((time.monotonic() - started) * 1000)
        return LLMResponse(
            content=content,
            provider=self.name,
            model="mock-1",
            input_tokens=len(input_text.split()),
            output_tokens=len(content.split()),
            latency_ms=latency_ms,
        )


def get_llm_provider() -> LLMProvider:
    if settings.llm_provider == "openai" and settings.openai_api_key:
        return OpenAILLMProvider(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            max_tokens=settings.llm_max_tokens,
        )
    if settings.llm_provider != "openai":
        logger.warning("unsupported_llm_provider provider=%s falling_back_to=mock", settings.llm_provider)
    return MockLLMProvider()


class LLMService:
    """Facade used by the rest of the app: generation + optional tracing."""

    def __init__(self, provider: LLMProvider | None = None):
        self.provider = provider or get_llm_provider()

    def generate_draft(
        self, *, instructions: str, input_text: str, trace_name: str, file_ids: list[str] | None = None
    ) -> LLMResponse:
        try:
            response = self.provider.generate(
                instructions=instructions, input_text=input_text, file_ids=file_ids
            )
        except Exception as exc:
            langfuse_client.record_llm_trace(
                name=trace_name,
                provider=self.provider.name,
                model=getattr(self.provider, "model", "unknown"),
                prompt=input_text,
                completion="",
                input_tokens=None,
                output_tokens=None,
                latency_ms=None,
                error=str(exc),
            )
            raise LLMProviderError(str(exc)) from exc

        trace_id = langfuse_client.record_llm_trace(
            name=trace_name,
            provider=response.provider,
            model=response.model,
            prompt=input_text,
            completion=response.content,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            latency_ms=response.latency_ms,
        )
        response.langfuse_trace_id = trace_id
        return response
