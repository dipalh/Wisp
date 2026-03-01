"""
Job Manager — Test Suite

Run from backend/:
    python -m tests.test_jobs
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from services.jobs import (
    JobStatus,
    create_job,
    get_job,
    list_jobs,
    update_job,
    clear,
)

_pass = 0
_fail = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global _pass, _fail
    status = "[PASS]" if condition else "[FAIL]"
    print(f"  {status}  {name}")
    if detail:
        print(f"         {detail}")
    if condition:
        _pass += 1
    else:
        _fail += 1


# ── Part 1: Job creation ──────────────────────────────────────────────────────

def test_create():
    print("\n" + "=" * 60)
    print("PART 1 — Job creation")
    print("=" * 60)

    clear()

    job = create_job("/some/folder")
    check("T1: job has an id", bool(job.id))
    check("T2: job starts PENDING", job.status == JobStatus.PENDING)
    check("T3: job root is stored", job.root == "/some/folder")
    check("T4: processed starts at 0", job.processed == 0)
    check("T5: total starts at 0", job.total == 0)
    check("T6: errors starts at 0", job.errors == 0)
    check("T7: candidates starts empty", job.candidates == [])

    job2 = create_job("/other/folder")
    check("T8: two distinct job ids", job.id != job2.id)
    check("T9: list_jobs returns both", len(list_jobs()) == 2)


# ── Part 2: Status transitions ────────────────────────────────────────────────

def test_status_transitions():
    print("\n" + "=" * 60)
    print("PART 2 — Status transitions")
    print("=" * 60)

    clear()
    job = create_job("/root")

    update_job(job.id, status=JobStatus.RUNNING, total=10)
    refreshed = get_job(job.id)
    check("T10: status set to RUNNING", refreshed.status == JobStatus.RUNNING)
    check("T11: total set to 10", refreshed.total == 10)

    update_job(job.id, processed=5, errors=1)
    refreshed = get_job(job.id)
    check("T12: processed set to 5", refreshed.processed == 5)
    check("T13: errors set to 1", refreshed.errors == 1)

    update_job(job.id, status=JobStatus.DONE)
    check("T14: status set to DONE", get_job(job.id).status == JobStatus.DONE)

    clear()
    job_f = create_job("/bad")
    update_job(job_f.id, status=JobStatus.FAILED, error_msg="disk full")
    refreshed = get_job(job_f.id)
    check("T15: status set to FAILED", refreshed.status == JobStatus.FAILED)
    check("T16: error_msg stored", refreshed.error_msg == "disk full")


# ── Part 3: Edge cases ────────────────────────────────────────────────────────

def test_edge_cases():
    print("\n" + "=" * 60)
    print("PART 3 — Edge cases")
    print("=" * 60)

    clear()

    # Unknown job_id doesn't crash
    update_job("nonexistent", status=JobStatus.DONE)
    check("T17: update on missing id is silent no-op", True)

    check("T18: get_job on missing id returns None", get_job("nonexistent") is None)

    # Candidates list updated atomically
    job = create_job("/root")
    fake_candidates = [{"path": "/root/a.tmp", "junk_score": 0.8}]
    update_job(job.id, candidates=fake_candidates)
    check("T19: candidates stored on job", get_job(job.id).candidates == fake_candidates)

    clear()
    check("T20: clear removes all jobs", list_jobs() == [])


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    test_create()
    test_status_transitions()
    test_edge_cases()

    print("\n" + "=" * 60)
    total = _pass + _fail
    if _fail == 0:
        print(f"  Results: {total}/{total} passed -- all good")
    else:
        print(f"  Results: {_pass}/{total} passed, {_fail} FAILED")
    print("=" * 60)
    sys.exit(1 if _fail else 0)


if __name__ == "__main__":
    main()
