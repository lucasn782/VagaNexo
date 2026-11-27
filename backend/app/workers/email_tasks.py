"""Celery tasks for asynchronous transactional email delivery and outbox recovery."""

from __future__ import annotations

import logging
import uuid

from app.auth.email_provider import build_email_provider
from app.auth.outbox import EmailOutboxService
from app.core.config import get_settings
from app.database.session import SessionLocal
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.workers.email_tasks.deliver_outbox_email",
    soft_time_limit=15,
    time_limit=30,
)
def deliver_outbox_email(outbox_id: str) -> bool:
    settings = get_settings()
    provider = build_email_provider(settings)
    parsed_id = uuid.UUID(outbox_id)
    with SessionLocal() as session:
        return EmailOutboxService.process_message(
            session,
            outbox_id=parsed_id,
            provider=provider,
            settings=settings,
        )


@celery_app.task(
    name="app.workers.email_tasks.sweep_email_outbox",
    soft_time_limit=30,
    time_limit=60,
)
def sweep_email_outbox() -> int:
    settings = get_settings()
    provider = build_email_provider(settings)
    with SessionLocal() as session:
        return EmailOutboxService.sweep_pending(
            session,
            provider=provider,
            settings=settings,
        )


def dispatch_outbox_email(outbox_id: uuid.UUID) -> None:
    """Best-effort dispatch to Celery after commit; periodic sweeper recovers on failure."""
    try:
        deliver_outbox_email.delay(str(outbox_id))
    except Exception:  # noqa: BLE001
        logger.warning(
            "Unable to dispatch outbox message %s to Celery; periodic sweeper will retry",
            outbox_id,
        )
