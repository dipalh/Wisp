from __future__ import annotations


def test_main_app_exposes_jobs_scan_surface_but_not_legacy_scan_routes():
    from main import app

    paths = {route.path for route in app.routes}

    assert "/api/v1/jobs/scan" in paths
    assert "/api/v1/jobs/{job_id}" in paths
    assert "/api/v1/jobs/indexed-files" in paths

    assert "/api/v1/scan" not in paths
    assert "/api/v1/scan/status" not in paths
    assert "/api/v1/scan/candidates" not in paths
