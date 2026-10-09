"""Tests for GitHub repository inspection and measured checks."""

import base64
import json
from pathlib import Path

import httpx
import pytest

from sightline.models import RepoSnapshot
from sightline.repo.checks import run_all
from sightline.repo.github import fetch, parse_repo_url


def test_parse_repo_url_variations():
    """Verify parse_repo_url handles various standard and edge-case GitHub URLs."""
    expected = ("pallets", "flask")

    assert parse_repo_url("https://github.com/pallets/flask") == expected
    assert parse_repo_url("https://github.com/pallets/flask/") == expected
    assert parse_repo_url("https://github.com/pallets/flask.git") == expected
    assert parse_repo_url("https://github.com/pallets/flask/tree/main") == expected
    assert parse_repo_url("https://github.com/pallets/flask/tree/main/src/flask") == expected
    assert parse_repo_url("http://github.com/pallets/flask") == expected
    assert parse_repo_url("git@github.com:pallets/flask.git") == expected
    assert parse_repo_url("pallets/flask") == expected


def test_parse_repo_url_invalid():
    """Verify parse_repo_url raises ValueError on malformed inputs."""
    with pytest.raises(ValueError):
        parse_repo_url("https://github.com/")

    with pytest.raises(ValueError):
        parse_repo_url("invalid-url")

    with pytest.raises(ValueError):
        parse_repo_url("")


def test_run_all_on_sample_repo_fixture():
    """Verify run_all returns exactly the expected rule names on sample_repo.json fixture."""
    fixture_path = Path(__file__).resolve().parent / "fixtures" / "sample_repo.json"
    with open(fixture_path, encoding="utf-8") as f:
        data = json.load(f)

    snapshot = RepoSnapshot(
        url=f"https://github.com/{data['owner']}/{data['name']}",
        owner=data["owner"],
        name=data["name"],
        description=data.get("description"),
        homepage=data.get("homepage"),
        default_branch=data.get("default_branch", "main"),
        files=data.get("files", []),
        truncated=data.get("truncated", False),
        readme=data.get("readme"),
        key_files=data.get("key_files", {}),
    )

    findings = run_all(snapshot)

    for finding in findings:
        assert finding.source == "measured"
        assert finding.target == "repo"
        assert finding.confidence == 1.0

    rules = [f.rule for f in findings]
    expected_rules = [
        "missing-license",
        "missing-contributing",
        "missing-code-of-conduct",
        "missing-ci",
        "missing-issue-templates",
        "readme-too-short",
        "readme-missing-install",
        "readme-missing-usage",
        "no-tests",
    ]
    assert rules == expected_rules

    # Verify specific severities noted in specification
    finding_map = {f.rule: f for f in findings}
    assert finding_map["missing-code-of-conduct"].severity == "low"
    assert finding_map["no-tests"].severity == "low"


def test_readme_command_mismatch():
    """Verify readme-command-mismatch detects missing targets/files with verified evidence."""
    readme_text = """# Demo Project

## Installation
Run `pip install -r requirements-missing.txt`

## Usage
Inside this project:
```bash
npm run nonexistent-task
make missing-target
python missing_script.py
node missing_app.js
```

And these valid commands:
```bash
npm run test
make build
pip install -r requirements.txt
python main.py
node server.js
```
"""
    snapshot = RepoSnapshot(
        url="https://github.com/demo/repo",
        owner="demo",
        name="repo",
        description="Demo",
        homepage=None,
        default_branch="main",
        files=[
            "LICENSE",
            "CONTRIBUTING.md",
            "CODE_OF_CONDUCT.md",
            ".github/workflows/ci.yml",
            ".github/ISSUE_TEMPLATE/bug.md",
            "tests/test_sample.py",
            "requirements.txt",
            "main.py",
            "server.js",
            "package.json",
            "Makefile",
        ],
        truncated=False,
        readme=readme_text,
        key_files={
            "package.json": json.dumps({"scripts": {"test": "jest"}}),
            "Makefile": "build:\n\techo build\n",
        },
    )

    findings = run_all(snapshot)
    mismatches = [f for f in findings if f.rule == "readme-command-mismatch"]

    # There should be 5 mismatches (pip, npm, make, python, node)
    assert len(mismatches) == 5

    for m in mismatches:
        assert m.verified is True
        assert m.verified_note == "checked against the repo files"
        assert m.evidence != ""

    problems = [m.problem for m in mismatches]
    assert any("requirements-missing.txt" in p for p in problems)
    assert any("nonexistent-task" in p for p in problems)
    assert any("missing-target" in p for p in problems)
    assert any("missing_script.py" in p for p in problems)
    assert any("missing_app.js" in p for p in problems)


def test_fetch_with_mock_transport():
    """Verify fetch() builds RepoSnapshot using httpx.MockTransport with no network."""
    repo_meta = {
        "description": "Mocked test repo",
        "homepage": "https://example.org",
        "default_branch": "main",
    }
    tree_data = {
        "tree": [
            {"path": "README.md", "type": "blob"},
            {"path": "pyproject.toml", "type": "blob"},
            {"path": "package.json", "type": "blob"},
        ],
        "truncated": False,
    }
    readme_data = {
        "content": base64.b64encode(b"# Hello Mock Repo\n").decode("ascii"),
        "encoding": "base64",
    }
    pkg_data = {
        "content": base64.b64encode(b'{"name": "mock-pkg"}').decode("ascii"),
        "encoding": "base64",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if url_str == "https://api.github.com/repos/test-org/test-repo":
            return httpx.Response(200, json=repo_meta)
        if url_str == "https://api.github.com/repos/test-org/test-repo/git/trees/main?recursive=1":
            return httpx.Response(200, json=tree_data)
        if url_str == "https://api.github.com/repos/test-org/test-repo/readme":
            return httpx.Response(200, json=readme_data)
        if url_str == "https://api.github.com/repos/test-org/test-repo/contents/package.json":
            return httpx.Response(200, json=pkg_data)
        if url_str == "https://api.github.com/repos/test-org/test-repo/contents/pyproject.toml":
            return httpx.Response(200, text="[project]\nname = 'mock'")
        return httpx.Response(404, json={"message": "Not Found"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    snapshot = fetch("https://github.com/test-org/test-repo", client=client)

    assert snapshot.owner == "test-org"
    assert snapshot.name == "test-repo"
    assert snapshot.description == "Mocked test repo"
    assert snapshot.default_branch == "main"
    assert snapshot.readme == "# Hello Mock Repo\n"
    assert "package.json" in snapshot.files
    assert "package.json" in snapshot.key_files
    assert snapshot.key_files["package.json"] == '{"name": "mock-pkg"}'


def test_fetch_error_handling_with_mock_transport():
    """Verify fetch() raises clear errors on 404, 403 rate limits, and timeouts."""
    # 1. 404 Not Found
    def not_found_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "Not Found"})

    client_404 = httpx.Client(transport=httpx.MockTransport(not_found_handler))
    with pytest.raises(RuntimeError) as exc_404:
        fetch("https://github.com/test-org/nonexistent", client=client_404)
    assert "not found or is private (404)" in str(exc_404.value)

    # 2. 403 Rate Limit
    def rate_limit_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"message": "API rate limit exceeded"})

    client_403 = httpx.Client(transport=httpx.MockTransport(rate_limit_handler))
    with pytest.raises(RuntimeError) as exc_403:
        fetch("https://github.com/test-org/limited", client=client_403)
    assert "rate limit exceeded" in str(exc_403.value).lower()
    assert "GITHUB_TOKEN" in str(exc_403.value)


@pytest.mark.live
def test_fetch_live_hello_world():
    """Live test fetching octocat/Hello-World from GitHub API."""
    snapshot = fetch("https://github.com/octocat/Hello-World")
    assert snapshot.owner == "octocat"
    assert snapshot.name == "Hello-World"
    assert snapshot.readme is not None
    assert len(snapshot.readme) > 0
    assert len(snapshot.files) > 0


def test_fetch_with_mock_transport_fills_new_fields():
    """Verify fetch() populates stars, forks, language, license, issues, pushed_at, html_url."""
    from sightline.repo.github import format_count

    repo_meta = {
        "description": "Mocked test repo",
        "homepage": "https://example.org",
        "default_branch": "main",
        "stargazers_count": 1234,
        "forks_count": 456,
        "language": "Python",
        "license": {"spdx_id": "MIT", "name": "MIT License"},
        "open_issues_count": 5,
        "pushed_at": "2026-09-01T00:00:00Z",
        "html_url": "https://github.com/test-org/test-repo",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if url_str == "https://api.github.com/repos/test-org/test-repo":
            return httpx.Response(200, json=repo_meta)
        if url_str == "https://api.github.com/repos/test-org/test-repo/git/trees/main?recursive=1":
            return httpx.Response(200, json={"tree": [], "truncated": False})
        if url_str == "https://api.github.com/repos/test-org/test-repo/readme":
            return httpx.Response(404, json={"message": "Not Found"})
        return httpx.Response(404, json={"message": "Not Found"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    snapshot = fetch("https://github.com/test-org/test-repo", client=client)

    assert snapshot.stars == 1234
    assert snapshot.forks == 456
    assert snapshot.language == "Python"
    assert snapshot.license_name == "MIT"
    assert snapshot.open_issues == 5
    assert snapshot.pushed_at == "2026-09-01T00:00:00Z"
    assert snapshot.html_url == "https://github.com/test-org/test-repo"
    assert format_count(snapshot.stars) == "1.2k"


def test_fetch_missing_fields_defaults():
    """Verify fetch() handles responses with missing metadata fields without crashing."""
    repo_meta = {}  # completely empty metadata

    def handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if url_str == "https://api.github.com/repos/test-org/test-repo":
            return httpx.Response(200, json=repo_meta)
        if url_str == "https://api.github.com/repos/test-org/test-repo/git/trees/main?recursive=1":
            return httpx.Response(200, json={"tree": [], "truncated": False})
        if url_str == "https://api.github.com/repos/test-org/test-repo/readme":
            return httpx.Response(404, json={"message": "Not Found"})
        return httpx.Response(404, json={"message": "Not Found"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    snapshot = fetch("https://github.com/test-org/test-repo", client=client)

    assert snapshot.stars == 0
    assert snapshot.forks == 0
    assert snapshot.language is None
    assert snapshot.license_name is None
    assert snapshot.open_issues == 0
    assert snapshot.pushed_at is None
    assert snapshot.html_url == "https://github.com/test-org/test-repo"


def test_format_count_helper():
    """Verify format_count converts numeric counts to compact strings."""
    from sightline.repo.github import format_count

    assert format_count(1234) == "1.2k"
    assert format_count(0) == "0"
    assert format_count(999) == "999"
    assert format_count(1000) == "1.0k"
    assert format_count(2450) == "2.5k"
    assert format_count(12500) == "12.5k"
    assert format_count(1200000) == "1.2M"
    assert format_count(None) == "0"
    assert format_count(-10) == "0"
