from celery import Celery

from app.core.config import get_settings


def create_celery() -> Celery:
    settings = get_settings()
    return Celery(
        "vaganexo",
        broker=settings.celery_broker_url,
        backend=settings.celery_result_backend,
        include=["app.workers.email_tasks"],
    )


celery_app = create_celery()
celery_app.conf.update(
    task_ignore_result=True,
    broker_connection_retry_on_startup=True,
    beat_schedule={
        "sweep-email-outbox-every-minute": {
            "task": "app.workers.email_tasks.sweep_email_outbox",
            "schedule": 60.0,
        },
    },
)
