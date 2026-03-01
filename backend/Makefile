.PHONY: test test-v lint

# Canonical test command — run this, not `pytest tests/`.
# Some legacy test files (test_deletable.py etc.) use custom runners
# and are not pytest-compatible.  This target runs only the supported
# pytest test suite.
TESTS = tests/test_job_db.py \
        tests/test_jobs_api.py \
        tests/test_scanner.py \
        tests/test_tagging_correctness.py \
        tests/test_sqlite_robustness.py \
        tests/test_pipeline_no_tag.py \
        tests/test_integration_scan.py

test:
	python -m pytest $(TESTS) -q

test-v:
	python -m pytest $(TESTS) -v

lint:
	python -m py_compile services/job_db.py
	python -m py_compile services/ingestor/scanner.py
	python -m py_compile services/os_tags/deletable.py
	python -m py_compile tasks/scan.py
	@echo "All files compile OK"
