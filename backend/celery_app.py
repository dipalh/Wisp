"""
Celery application instance for Wisp.

Broker: Redis on localhost:6379/0
Result backend: Redis on localhost:6379/1

Start the worker with:
    cd backend && source venv/bin/activate
    celery -A celery_app worker --loglevel=info
"""
import sys
from pathlib import Path

# Ensure the backend/ directory is on sys.path so that `services.*` and
# `tasks.*` are importable when Celery CLI is invoked from backend/.
_backend_dir = str(Path(__file__).resolve().parent)
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from celery import Celery

app = Celery(
    "wisp",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/1",
    include=["tasks.scan"],
)

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

