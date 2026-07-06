"""Optional Langfuse integration.

The app must work fully with LANGFUSE_ENABLED=false (the default) and without
the `langfuse` package being configured with real credentials. This module is
the single place that talks to the Langfuse SDK, so llm_service.py stays
provider-agnostic and doesn't need to special-case observability.
"""

from typing import Any

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_client: Any | None = None
_client_initialized = False


def _get_client() -> Any | None:
    global _client, _client_initialized
    if _client_initialized:
        return _client
    _client_initialized = True

    if not settings.langfuse_enabled:
        return None

    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        logger.warning("langfuse_enabled_but_missing_keys")
        return None

    try:
        from langfuse import Langfuse

        _client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
    except Exception as exc:  # noqa: BLE001 - observability must never break the app
        logger.error("langfuse_init_failed error=%s", exc)
        _client = None

    return _client


def record_llm_trace(
    *,
    name: str,
    provider: str,
    model: str,
    prompt: str,
    completion: str,
    input_tokens: int | None,
    output_tokens: int | None,
    latency_ms: int | None,
    metadata: dict[str, Any] | None = None,
    error: str | None = None,
) -> str | None:
    """Record a generation in Langfuse if enabled/configured. Returns the trace id, if any."""
    client = _get_client()
    if client is None:
        return None

    try:
        trace = client.trace(name=name, metadata=metadata or {})
        trace.generation(
            name=f"{provider}:{model}",
            model=model,
            input=prompt,
            output=completion,
            usage={"input": input_tokens, "output": output_tokens},
            metadata={"latency_ms": latency_ms, "error": error} if error else {"latency_ms": latency_ms},
            level="ERROR" if error else "DEFAULT",
        )
        return trace.id
    except Exception as exc:  # noqa: BLE001 - observability must never break the app
        logger.error("langfuse_record_trace_failed error=%s", exc)
        return None
