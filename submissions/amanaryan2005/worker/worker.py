"""
Celery Application — DocuMind Document Ingestion Worker
"""
import os
from dotenv import load_dotenv
load_dotenv()

from celery import Celery

app = Celery("documind")

app.conf.update(
    broker_url=os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0"),
    result_backend=os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/1"),
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    broker_connection_retry_on_startup=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    imports=["worker.tasks", "tasks"],
)

try:
    import worker.tasks  # noqa
except ImportError:
    try:
        import tasks  # noqa
    except ImportError:
        pass

app.autodiscover_tasks(["worker"])
