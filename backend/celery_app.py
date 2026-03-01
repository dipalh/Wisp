"""
Celery application instance for Wisp.

Broker: Redis on localhost:6379/0
Result backend: Redis on localhost:6379/1

Start the worker with:
    celery -A celery_app worker --loglevel=info
"""
from celery import Celery

app = Celery(
    "wisp",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/1",
)

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

# Auto-discover tasks in the `tasks` package
app.autodiscover_tasks(["tasks"])
