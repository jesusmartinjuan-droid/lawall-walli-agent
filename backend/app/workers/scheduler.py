"""Celery Beat schedule definition, kept separate from celery_app.py so the
polling cadence (driven by MAIL_POLL_INTERVAL_SECONDS) is easy to find."""

from app.core.config import settings

BEAT_SCHEDULE = {
    "poll-active-mailboxes": {
        "task": "app.workers.tasks.poll_active_mailboxes",
        "schedule": float(settings.mail_poll_interval_seconds),
    },
    "refresh-active-web-sources": {
        "task": "app.workers.tasks.refresh_active_web_sources",
        "schedule": float(settings.web_source_poll_interval_seconds),
    },
}
