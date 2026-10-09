"""Tests for end-to-end pipeline and CLI execution."""

import json

import pytest

from sightline.cli import main as cli_main
from sightline.models import RepoSnapshot
from sightline.pipeline import run
from sightline.repo import github


@pytest.mark.browser
def test_pipeline_site_mode(fixtures_server, tmp_path):
    steps = []
    page_url = f"{fixtures_server}/page.html"
    result = run(
        mode="site",
        url=page_url,
        out_dir=tmp_path,
        on_step=steps.append,
    )

    expected_steps = [
        "Opening website",
        "Taking screenshot",
        "Running checks",
        "Marking elements",
        "Asking Gemma",
        "Drawing results",
        "Writing issues",
    ]
    assert steps == expected_steps
    assert result.mode == "site"
    assert (tmp_path / "result.json").exists()
    assert (tmp_path / "annotated.png").exists()

    # Verify findings, stats, and issues
    assert len(result.findings) >= 3
    assert result.stats["total_findings"] == len(result.findings)
    assert len(result.issues) == len(result.findings)
    for f in result.findings:
        assert f.id in result.issues
        assert len(result.issues[f.id]) > 0

    # Verify JSON content matches
    saved_data = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    assert saved_data["mode"] == "site"
    assert len(saved_data["findings"]) == len(result.findings)


def test_pipeline_repo_mode(monkeypatch, tmp_path):
    mock_repo = RepoSnapshot(
        url="https://github.com/mock-org/mock-repo",
        owner="mock-org",
        name="mock-repo",
        description="A mock repository for testing",
        homepage=None,
        default_branch="main",
        files=["README.md", "pyproject.toml"],
        truncated=False,
        readme="# Mock Repo\n\nRun:\n```bash\npython run.py\n```\n",
        key_files={"README.md": "# Mock Repo\n\nRun:\n```bash\npython run.py\n```\n"},
    )
    monkeypatch.setattr(github, "fetch", lambda *args, **kwargs: mock_repo)

    steps = []
    result = run(
        mode="repo",
        url="https://github.com/mock-org/mock-repo",
        out_dir=tmp_path,
        on_step=steps.append,
    )

    expected_steps = [
        "Fetching repository",
        "Running checks",
        "Asking Gemma",
        "Writing issues",
    ]
    assert steps == expected_steps
    assert result.mode == "repo"
    assert (tmp_path / "result.json").exists()
    assert len(result.findings) > 0
    assert result.stats["total_findings"] == len(result.findings)
    assert len(result.issues) == len(result.findings)


def test_pipeline_gemma_none_fallback(monkeypatch, tmp_path):
    mock_repo = RepoSnapshot(
        url="https://github.com/mock-org/mock-repo",
        owner="mock-org",
        name="mock-repo",
        description="A mock repository for testing",
        homepage=None,
        default_branch="main",
        files=["README.md"],
        truncated=False,
        readme="# Mock Repo\n",
        key_files={"README.md": "# Mock Repo\n"},
    )
    monkeypatch.setattr(github, "fetch", lambda *args, **kwargs: mock_repo)

    # Force Gemma to return None
    monkeypatch.setattr("sightline.gemma_review.ask_json", lambda *a, **kw: None)

    result = run(
        mode="repo",
        url="https://github.com/mock-org/mock-repo",
        out_dir=tmp_path,
    )

    # Pipeline still finishes successfully and returns measured findings
    assert result is not None
    assert len(result.findings) > 0
    assert all(f.source == "measured" for f in result.findings)
    assert (tmp_path / "result.json").exists()


def test_cli_execution(monkeypatch, tmp_path):
    mock_repo = RepoSnapshot(
        url="https://github.com/mock-org/mock-repo",
        owner="mock-org",
        name="mock-repo",
        description="A mock repository for testing",
        homepage=None,
        default_branch="main",
        files=["README.md", "pyproject.toml"],
        truncated=False,
        readme="# Mock Repo\n\nRun:\n```bash\npython run.py\n```\n",
        key_files={"README.md": "# Mock Repo\n\nRun:\n```bash\npython run.py\n```\n"},
    )
    monkeypatch.setattr(github, "fetch", lambda *args, **kwargs: mock_repo)

    exit_code = cli_main(
        ["repo", "https://github.com/mock-org/mock-repo", "--out", str(tmp_path), "--mock"]
    )
    assert exit_code == 0
    assert (tmp_path / "result.json").exists()

    issues_dir = tmp_path / "issues"
    assert issues_dir.is_dir()
    issue_files = list(issues_dir.glob("*.md"))
    assert len(issue_files) > 0
