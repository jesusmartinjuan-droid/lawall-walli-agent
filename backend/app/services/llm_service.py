"""LLM abstraction layer.

The rest of the app depends only on `LLMService` / `LLMProvider`, never on a
concrete SDK (e.g. `openai`) directly. Swapping providers (Anthropic, local
models, etc.) means adding a new `LLMProvider` implementation and wiring it
into `get_llm_provider()` — no changes needed in processing_service.py.
"""

from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.core.config import settings
from app.core.logging import get_logger
from app.core.retry import with_retry
from app.services import langfuse_client

logger = get_logger(__name__)


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
    cached_tokens: int | None = None


class LLMProviderError(Exception):
    pass


class LLMProvider(ABC):
    name: str

    @abstractmethod
    def generate(
        self, *, system_prompt: str, user_prompt: str, response_schema: dict | None = None
    ) -> LLMResponse: ...


class OpenAILLMProvider(LLMProvider):
    name = "openai"

    def __init__(self, api_key: str, model: str, temperature: float, max_tokens: int):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._api_key = api_key

    def _client(self):
        from openai import OpenAI

        return OpenAI(api_key=self._api_key)

    def generate(
        self, *, system_prompt: str, user_prompt: str, response_schema: dict | None = None
    ) -> LLMResponse:
        def _call():
            client = self._client()
            kwargs = {}
            if response_schema is not None:
                kwargs["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "walli_structured_output",
                        "schema": response_schema,
                        "strict": True,
                    },
                }
            return client.chat.completions.create(
                model=self.model,
                temperature=self.temperature,
                max_completion_tokens=self.max_tokens,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                **kwargs,
            )

        started = time.monotonic()
        completion = with_retry(_call, exceptions=(Exception,))
        latency_ms = int((time.monotonic() - started) * 1000)

        choice = completion.choices[0]
        usage = completion.usage
        prompt_tokens = getattr(usage, "prompt_tokens", None)
        cached_tokens = getattr(getattr(usage, "prompt_tokens_details", None), "cached_tokens", None)

        if prompt_tokens:
            logger.info(
                "openai_prompt_cache model=%s prompt_tokens=%s cached_tokens=%s",
                self.model,
                prompt_tokens,
                cached_tokens or 0,
            )

        return LLMResponse(
            content=choice.message.content or "",
            provider=self.name,
            model=self.model,
            input_tokens=prompt_tokens,
            output_tokens=getattr(usage, "completion_tokens", None),
            latency_ms=latency_ms,
            cached_tokens=cached_tokens,
        )


def _mock_structured_stub(schema: dict, draft_text: str) -> dict:
    """Builds a minimal, schema-shaped JSON object for MockLLMProvider,
    generically from `response_schema["properties"]`, so any structured
    output shape (present or future) works locally without an API key and
    without hardcoding a stub per schema here. The "draft" string property,
    if present, gets the canned draft text; everything else gets a
    conservative empty/default value (preferring an explicit "none" enum
    member when the schema declares one, since that's the safe "nothing to
    do" choice for the kind of yes/no/which-option fields these schemas add
    alongside "draft")."""
    properties = schema.get("properties", {})
    result: dict = {}
    for name, prop_schema in properties.items():
        if name == "draft" and prop_schema.get("type") == "string":
            result[name] = draft_text
            continue
        if "enum" in prop_schema:
            enum_values = prop_schema["enum"]
            result[name] = "none" if "none" in enum_values else (enum_values[0] if enum_values else "")
        elif prop_schema.get("type") == "array":
            result[name] = []
        elif prop_schema.get("type") == "string":
            result[name] = ""
        elif prop_schema.get("type") in ("integer", "number"):
            result[name] = 0
        elif prop_schema.get("type") == "boolean":
            result[name] = False
        else:
            result[name] = None
    return result


class MockLLMProvider(LLMProvider):
    """Deterministic fallback used when no LLM_PROVIDER API key is configured.

    Keeps local development and tests functional without real credentials.
    """

    name = "mock"

    def generate(
        self, *, system_prompt: str, user_prompt: str, response_schema: dict | None = None
    ) -> LLMResponse:
        started = time.monotonic()
        draft = (
            "Gracias por tu mensaje. Estamos revisando tu consulta y te "
            "responderemos con la información necesaria en cuanto la tengamos "
            "disponible.\n\n[Borrador generado por el proveedor LLM 'mock': "
            "configura OPENAI_API_KEY para generar respuestas reales.]"
        )
        content = json.dumps(_mock_structured_stub(response_schema, draft)) if response_schema else draft
        latency_ms = int((time.monotonic() - started) * 1000)
        return LLMResponse(
            content=content,
            provider=self.name,
            model="mock-1",
            input_tokens=len(user_prompt.split()),
            output_tokens=len(content.split()),
            latency_ms=latency_ms,
        )


def get_llm_provider() -> LLMProvider:
    if settings.llm_provider == "openai" and settings.openai_api_key:
        return OpenAILLMProvider(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            temperature=settings.llm_temperature,
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
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        trace_name: str,
        response_schema: dict | None = None,
    ) -> LLMResponse:
        try:
            response = self.provider.generate(
                system_prompt=system_prompt, user_prompt=user_prompt, response_schema=response_schema
            )
        except Exception as exc:
            langfuse_client.record_llm_trace(
                name=trace_name,
                provider=self.provider.name,
                model=getattr(self.provider, "model", "unknown"),
                prompt=user_prompt,
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
            prompt=user_prompt,
            completion=response.content,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            latency_ms=response.latency_ms,
        )
        response.langfuse_trace_id = trace_id
        return response
