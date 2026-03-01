#!/usr/bin/env bash
# Canonical test command for the Wisp backend.
# Usage: ./run_tests.sh        (quiet)
#        ./run_tests.sh -v     (verbose)
set -e
cd "$(dirname "$0")"

TESTS=(
  tests/test_job_db.py
  tests/test_jobs_api.py
  tests/test_scanner.py
  tests/test_tagging_correctness.py
  tests/test_sqlite_robustness.py
  tests/test_pipeline_no_tag.py
  tests/test_integration_scan.py
)

python -m pytest "${TESTS[@]}" "$@"
