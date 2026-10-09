"""Tests for FastAPI web backend and job runner."""

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sightline.models import AnalysisResult, Box, Finding
from web import jobs
from web.app import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_job_store():
    """Ensure in-memory job store is empty before each test."""
    jobs.clear_jobs()
    yield
    jobs.clear_jobs()


def test_health_check():
    """Verify GET /api/health returns 200 and ok status."""
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_invalid_inputs_return_400():
    """Verify input validation returns 400 with descriptive error details."""
    # 1. URL length exceeding 300 characters
    long_url = "https://example.com/" + "a" * 300
    res = client.post("/api/analyze", json={"mode": "site", "url": long_url})
    assert res.status_code == 400
    assert "exceeds maximum of 300" in res.json()["detail"]

    # 2. Empty URL
    res = client.post("/api/analyze", json={"mode": "site", "url": "   "})
    assert res.status_code == 400

    # 3. Invalid mode
    res = client.post("/api/analyze", json={"mode": "desktop", "url": "https://example.com"})
    assert res.status_code == 400
    assert "Must be either 'site' or 'repo'" in res.json()["detail"]

    # 4. Repo mode with non-github domain
    res = client.post("/api/analyze", json={"mode": "repo", "url": "https://gitlab.com/owner/repo"})
    assert res.status_code == 400
    assert "github.com links" in res.json()["detail"]

    # 5. Repo mode with non-http/https scheme
    res = client.post("/api/analyze", json={"mode": "repo", "url": "ssh://github.com/owner/repo"})
    assert res.status_code == 400

    # 6. Site mode with non-http/https scheme
    res = client.post("/api/analyze", json={"mode": "site", "url": "ftp://example.com"})
    assert res.status_code == 400


def test_concurrency_limit_400():
    """Verify submitting when 5 active jobs are queued/running returns 400."""
    with jobs._lock:
        for i in range(5):
            jobs.JOBS[f"mock-job-{i}"] = {
                "id": f"mock-job-{i}",
                "status": "running",
                "step": "Processing",
                "result": None,
                "error": None,
            }

    res = client.post("/api/analyze", json={"mode": "site", "url": "https://example.com"})
    assert res.status_code == 400
    assert "At most 5 concurrent jobs" in res.json()["detail"]


def test_unknown_job_returns_404():
    """Verify requesting an unknown job ID returns 404."""
    res = client.get("/api/jobs/nonexistent-id-999")
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()


def test_job_lifecycle_with_monkeypatched_pipeline(monkeypatch):
    """Verify starting job, polling until done, and validating result matches sample keys."""
    sample_path = Path(__file__).resolve().parent.parent / "web" / "sample_result.json"
    with open(sample_path, encoding="utf-8") as f:
        sample_data = json.load(f)

    def mock_run(mode, url, out_dir=None, on_step=None, with_site=False):
        if on_step:
            on_step("Simulating checks")
        findings = [
            Finding(
                id=f["id"],
                source=f["source"],
                target=f["target"],
                rule=f["rule"],
                severity=f["severity"],
                problem=f["problem"],
                why_it_matters=f["why_it_matters"],
                fix=f["fix"],
                fix_snippet=f.get("fix_snippet"),
                fix_value=f.get("fix_value"),
                evidence=f.get("evidence", ""),
                confidence=f.get("confidence", 1.0),
                element_number=f.get("element_number"),
                box=Box(**f["box"]) if f.get("box") else None,
                file_path=f.get("file_path"),
                verified=f.get("verified", False),
                verified_note=f.get("verified_note"),
            )
            for f in sample_data["findings"]
        ]
        return AnalysisResult(
            mode=sample_data["mode"],
            url=sample_data["url"],
            title=sample_data["title"],
            findings=findings,
            annotated_image=sample_data.get("annotated_image"),
            issues=sample_data.get("issues", {}),
            notes=sample_data.get("notes", []),
            stats=sample_data.get("stats", {}),
        )

    monkeypatch.setattr("web.jobs.run", mock_run)

    # 1. Start job
    start_resp = client.post(
        "/api/analyze",
        json={"mode": "site", "url": "https://example.com"},
    )
    assert start_resp.status_code == 200
    job_id = start_resp.json()["job_id"]
    assert bool(job_id)

    # 2. Poll until done
    for _ in range(50):
        poll_resp = client.get(f"/api/jobs/{job_id}")
        assert poll_resp.status_code == 200
        data = poll_resp.json()
        if data["status"] == "done":
            break
        time.sleep(0.05)
    else:
        pytest.fail("Job did not finish in time")

    assert data["status"] == "done"
    assert "result" in data
    result = data["result"]

    # Verify keys match sample_result.json keys
    assert set(result.keys()) == set(sample_data.keys())
    assert len(result["findings"]) == len(sample_data["findings"])
    assert result["title"] == sample_data["title"]


def test_static_routes_and_file_serving():
    """Verify root / serves index.html and /files serves generated output."""
    # 1. Root UI page
    res = client.get("/")
    assert res.status_code == 200
    assert "<title>SightLine</title>" in res.text

    # 2. Static CSS file
    res_css = client.get("/static/style.css")
    assert res_css.status_code == 200

    # 3. Output files mounting at /files
    from sightline.config import settings

    test_file = settings.out_dir / "test_artifact.txt"
    test_file.write_text("artifact content", encoding="utf-8")
    try:
        res_file = client.get("/files/test_artifact.txt")
        assert res_file.status_code == 200
        assert res_file.text == "artifact content"
    finally:
        if test_file.exists():
            test_file.unlink()


def test_job_partial_results():
    """Verify that get_job surfaces partial findings while job status is running."""
    with jobs._lock:
        jobs.JOBS["test-partial-job"] = {
            "id": "test-partial-job",
            "status": "running",
            "step": "Asking Gemma",
            "partial": {
                "partial": True,
                "findings": [{"id": "site-001", "rule": "low-contrast"}],
            },
            "result": None,
            "error": None,
        }

    job_data = jobs.get_job("test-partial-job")
    assert job_data is not None
    assert job_data["status"] == "running"
    assert "partial" in job_data
    assert job_data["partial"]["partial"] is True
    assert len(job_data["partial"]["findings"]) == 1

    # When job finishes, partial is not returned in get_job (full result takes over)
    with jobs._lock:
        jobs.JOBS["test-partial-job"]["status"] = "done"
        jobs.JOBS["test-partial-job"]["result"] = {"mode": "site", "findings": []}

    job_data_done = jobs.get_job("test-partial-job")
    assert job_data_done["status"] == "done"
    assert "partial" not in job_data_done
    assert "result" in job_data_done


def test_jobs_unique_folders(monkeypatch):
    """Verify two consecutive jobs write to different out/<job_id>/ folders
    and return different /files/<job_id>/ URLs.
    """
    from sightline.config import settings

    captured_out_dirs = []

    def mock_run(mode, url, out_dir=None, on_step=None, with_site=False, on_partial=None):
        captured_out_dirs.append(out_dir)
        if out_dir:
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "annotated.png").write_text("dummy image", encoding="utf-8")
        return AnalysisResult(
            mode="site",
            url=url,
            title="Test",
            findings=[],
            annotated_image=str(out_dir / "annotated.png") if out_dir else None,
            issues={},
            notes=[],
            stats={},
        )

    monkeypatch.setattr("web.jobs.run", mock_run)

    # Job 1
    r1 = client.post("/api/analyze", json={"mode": "site", "url": "https://example.com/1"})
    assert r1.status_code == 200
    job1_id = r1.json()["job_id"]

    for _ in range(50):
        data1 = client.get(f"/api/jobs/{job1_id}").json()
        if data1["status"] == "done":
            break
        time.sleep(0.05)
    assert data1["status"] == "done"

    # Job 2
    r2 = client.post("/api/analyze", json={"mode": "site", "url": "https://example.com/2"})
    assert r2.status_code == 200
    job2_id = r2.json()["job_id"]

    for _ in range(50):
        data2 = client.get(f"/api/jobs/{job2_id}").json()
        if data2["status"] == "done":
            break
        time.sleep(0.05)
    assert data2["status"] == "done"

    assert job1_id != job2_id
    assert captured_out_dirs[0] != captured_out_dirs[1]
    assert captured_out_dirs[0] == settings.out_dir / job1_id
    assert captured_out_dirs[1] == settings.out_dir / job2_id

    url1 = data1["result"]["annotated_image"]
    url2 = data2["result"]["annotated_image"]
    assert url1 != url2
    assert url1 == f"/files/{job1_id}/annotated.png"
    assert url2 == f"/files/{job2_id}/annotated.png"


def test_files_endpoint_traversal():
    """Verify that path traversal attempts on /files return 404 or 403."""
    res = client.get("/files/../../etc/passwd")
    assert res.status_code in (403, 404)

    res_encoded = client.get("/files/..%2F..%2Fetc/passwd")
    assert res_encoded.status_code in (403, 404)

