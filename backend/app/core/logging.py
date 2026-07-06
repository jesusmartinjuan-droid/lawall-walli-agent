"""Structured logging configuration shared by the API and the worker."""

import logging
import sys

from app.core.config import settings

_LOG_FORMAT = (
    '{"timestamp": "%(asctime)s", "level": "%(levelname)s", "logger": "%(name)s", '
    '"message": "%(message)s"}'
)


def configure_logging() -> None:
    """Configure root logging handlers. Safe to call multiple times."""
    root = logging.getLogger()
    if root.handlers:
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt="%Y-%m-%dT%H:%M:%S%z"))

    root.setLevel(settings.log_level.upper())
    root.addHandler(handler)

    # Quiet down noisy third-party loggers unless we're debugging.
    for noisy_logger in ("uvicorn.access", "httpx", "httpcore"):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(name)
