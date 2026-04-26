from celery import Celery
from app.config import settings

celery = Celery(
    "studymate",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.workers.tasks"],
)
celery.conf.update(
    task_routes={"app.workers.tasks.ingest_*": {"queue": "ingest"}},
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_default_queue="default",
)
