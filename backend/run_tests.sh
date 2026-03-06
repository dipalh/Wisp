#!/usr/bin/env bash
# Canonical test command for the Wisp backend.
# Usage: ./run_tests.sh        (quiet)
#        ./run_tests.sh -v     (verbose)
set -e
cd "$(dirname "$0")"
PYTHON_BIN="./venv/bin/python"

if [ ! -x "$PYTHON_BIN" ]; then
  echo "Missing backend virtualenv interpreter at $PYTHON_BIN" >&2
  exit 1
fi

TESTS=(
  tests/test_job_db.py
  tests/test_jobs_api.py
  tests/test_scanner.py
  tests/test_tagging_correctness.py
  tests/test_sqlite_robustness.py
  tests/test_pipeline_no_tag.py
  tests/test_integration_scan.py
  tests/test_search_api.py
)

"$PYTHON_BIN" -m pytest "${TESTS[@]}" "$@"
