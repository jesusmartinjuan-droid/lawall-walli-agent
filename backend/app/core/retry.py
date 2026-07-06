"""Shared retry policy for flaky external operations (IMAP, LLM calls, draft creation).

Centralised so `MAX_RETRY_ATTEMPTS` behaves consistently everywhere, with a
simple exponential backoff between attempts.
"""

from collections.abc import Callable
from typing import TypeVar

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import settings

T = TypeVar("T")


def with_retry(
    func: Callable[[], T],
    *,
    exceptions: tuple[type[Exception], ...] = (Exception,),
    max_attempts: int | None = None,
) -> T:
    """Execute `func` with exponential-backoff retries, re-raising the last error."""
    attempts = max_attempts or settings.max_retry_attempts

    @retry(
        stop=stop_after_attempt(attempts),
        wait=wait_exponential(multiplier=1, min=1, max=15),
        retry=retry_if_exception_type(exceptions),
        reraise=True,
    )
    def _runner() -> T:
        return func()

    return _runner()
