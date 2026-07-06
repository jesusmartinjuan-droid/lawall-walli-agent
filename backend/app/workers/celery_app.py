"""Celery application used by both the worker and beat processes.

Run with:
    celery -A app.workers.celery_app worker --loglevel=info
    celery -A app.workers.celery_app beat --loglevel=info
"""

from celery import Celery

from app.core.config import settings
from app.core.logging import configure_logging

# See app/main.py for why this must be imported before any ORM usage.
from app.db import base_all  # noqa: F401
from app.workers.scheduler import BEAT_SCHEDULE

configure_logging()

celery_app = Celery(
    "walli",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    beat_schedule=BEAT_SCHEDULE,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)
