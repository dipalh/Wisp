"""
Dummy scan Celery task — proves the job spine works.

Simulates a 50-step scan with 0.2s sleep per step.
Replace the loop body with real scan_and_index() later.
"""
import time
import traceback

from celery_app import app
from services.job_db import set_status, update_progress


@app.task(name="tasks.dummy_scan")
def dummy_scan(job_id: str) -> None:
    """Simulate a long-running scan job."""
    try:
        set_status(job_id, "running")

        total = 50
        for i in range(total):
            time.sleep(0.2)  # simulate work
            update_progress(job_id, i + 1, total, f"Processing file {i + 1}")

        set_status(job_id, "success", "Scan complete")

    except Exception:
        set_status(job_id, "failed", traceback.format_exc(limit=3))
