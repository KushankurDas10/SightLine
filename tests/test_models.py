"""Tests for sightline.models data structures."""

from dataclasses import asdict

from sightline.models import (
    AnalysisResult,
    Box,
    Element,
    Finding,
    PageSnapshot,
    RepoSnapshot,
)


def test_box_and_element_serialization():
    box = Box(x=10.0, y=20.0, w=100.0, h=40.0)
    element = Element(
        number=1,
        selector="button#submit",
        tag="button",
        text="Submit",
        box=box,
        name="Submit Form",
        meta={"kind": "interactive", "color": "#ffffff", "background": "#000000"},
    )
    data = asdict(element)
    assert data["number"] == 1
    assert data["box"]["x"] == 10.0
    assert data["box"]["w"] == 100.0
    assert data["name"] == "Submit Form"
    assert data["meta"]["kind"] == "interactive"


def test_snapshots():
    page = PageSnapshot(
        url="https://example.com",
        screenshot_path="/tmp/shot.png",
        page_width=1280,
        page_height=800,
        elements=[],
        lang="en",
        title="Example Domain",
    )
    assert page.lang == "en"
    assert page.title == "Example Domain"

    repo = RepoSnapshot(
        url="https://github.com/org/repo",
        owner="org",
        name="repo",
        description="A great repo",
        homepage=None,
        default_branch="main",
        files=["README.md", "pyproject.toml"],
        truncated=False,
        readme="# Hello",
        key_files={"README.md": "# Hello"},
    )
    assert repo.owner == "org"
    assert "README.md" in repo.key_files


def test_finding_and_analysis_result():
    finding = Finding(
        id="finding-1",
        source="measured",
        target="site",
        rule="contrast",
        severity="high",
        problem="Low contrast text",
        why_it_matters="Hard to read",
        fix="Darken text color",
        evidence="Contrast ratio is 2.5:1",
        confidence=1.0,
        element_number=1,
    )
    result = AnalysisResult(
        mode="site",
        url="https://example.com",
        title="Example",
        findings=[finding],
        issues={"finding-1": "# Issue title\nProblem details"},
        stats={"total_findings": 1},
    )
    finding_dict = asdict(finding)
    assert finding_dict["id"] == "finding-1"
    assert finding_dict["source"] == "measured"

    result_dict = asdict(result)
    assert result_dict["mode"] == "site"

    serialized = result.to_dict()
    assert serialized["mode"] == "site"
    assert len(serialized["findings"]) == 1
    assert serialized["findings"][0]["id"] == "finding-1"
    assert serialized["issues"]["finding-1"].startswith("# Issue title")
