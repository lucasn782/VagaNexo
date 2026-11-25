from celery import Celery

from app.core.config import get_settings


def create_celery() -> Celery:
    settings = get_settings()
    return Celery(
        "vaganexo",
        broker=settings.celery_broker_url,
        backend=settings.celery_result_backend,
    )


celery_app = create_celery()
celery_app.conf.update(
    task_ignore_result=True,
    broker_connection_retry_on_startup=True,
)
