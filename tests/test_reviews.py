"""Tests for Gemma reviews, enrichment, evidence verification, merge, and issue generation."""

import json
from pathlib import Path

import pytest

from sightline.gemma_review import normalize_text, review_repo, review_site
from sightline.issues import to_issue
from sightline.merge import merge_findings
from sightline.models import Box, Element, Finding, PageSnapshot, RepoSnapshot

# ---------------------------------------------------------------------------
# 1. Enrichment applied
# ---------------------------------------------------------------------------


def test_enrichment_applied(monkeypatch, tmp_path):
    # Hand-made snapshot and measured finding
    el = Element(
        number=1,
        selector="button#submit",
        tag="button",
        text="Submit",
        box=Box(x=10, y=10, w=100, h=40),
        name="Submit",
        meta={"kind": "interactive"},
    )
    img_path = tmp_path / "test.png"
    img_path.write_bytes(b"\x89PNG\r\n\x1a\n")

    snapshot = PageSnapshot(
        url="http://example.local",
        screenshot_path=str(img_path),
        page_width=1280,
        page_height=800,
        elements=[el],
    )

    measured = [
        Finding(
            id="site-001",
            source="measured",
            target="site",
            rule="low-contrast",
            severity="high",
            problem="Text contrast ratio 2.0:1 is too low.",
            why_it_matters="Old explanation",
            fix="Old fix",
            element_number=1,
        )
    ]

    mock_response = {
        "enrich": [
            {
                "id": "site-001",
                "why_it_matters": "Enriched: Low contrast severely degrades readability.",
                "fix": "Enriched: Change text color to dark blue.",
                "fix_snippet": "color: #1e3a8a;",
                "fix_value": "#1e3a8a",
            }
        ],
        "new_findings": [],
    }

    monkeypatch.setattr("sightline.gemma_review.ask_json", lambda *a, **kw: mock_response)

    results = review_site(snapshot, img_path, measured)
    assert len(results) == 1
    enriched = results[0]
    assert enriched.id == "site-001"
    assert enriched.why_it_matters == "Enriched: Low contrast severely degrades readability."
    assert enriched.fix == "Enriched: Change text color to dark blue."
    assert enriched.fix_snippet == "color: #1e3a8a;"
    assert enriched.fix_value == "#1e3a8a"
    assert enriched.verified is True


# ---------------------------------------------------------------------------
# 2. Evidence validation (present, absent, whitespace differences)
# ---------------------------------------------------------------------------


def test_repo_evidence_validation(monkeypatch):
    readme_text = "# Sample Project\n\nRun tests:\n```bash\npytest  -v\n```\n"
    repo = RepoSnapshot(
        url="https://github.com/example/repo",
        owner="example",
        name="repo",
        description="A sample test repository",
        homepage=None,
        default_branch="main",
        files=["README.md", "pyproject.toml"],
        truncated=False,
        readme=readme_text,
        key_files={"README.md": readme_text, "pyproject.toml": "[project]\nname = 'sample'\n"},
    )

    mock_response = {
        "summary": "Sample test repo.",
        "enrich": [],
        "new_findings": [
            # 1. Exact quote present
            {
                "file_path": "README.md",
                "rule": "readme-clarity",
                "severity": "medium",
                "problem": "Mentions verbose tests flag",
                "why_it_matters": "Extra output",
                "fix": "Remove -v",
                "evidence": "pytest  -v",
                "confidence": 0.9,
            },
            # 2. Quote with whitespace differences (single space vs double space/newlines)
            {
                "file_path": "README.md",
                "rule": "readme-clarity",
                "severity": "low",
                "problem": "Run tests prompt formatting",
                "why_it_matters": "Readability",
                "fix": "Clean up",
                "evidence": "Run   tests:\n```bash",
                "confidence": 0.85,
            },
            # 3. Quote absent (hallucination)
            {
                "file_path": "README.md",
                "rule": "hallucinated-rule",
                "severity": "high",
                "problem": "Cargo test is missing",
                "why_it_matters": "Build fail",
                "fix": "Add cargo",
                "evidence": "cargo build --release",
                "confidence": 0.95,
            },
            # 4. Empty evidence
            {
                "file_path": "README.md",
                "rule": "no-evidence-rule",
                "severity": "high",
                "problem": "No evidence provided",
                "evidence": "",
                "confidence": 0.9,
            },
        ],
    }

    monkeypatch.setattr("sightline.gemma_review.ask_json", lambda *a, **kw: mock_response)

    findings = review_repo(repo, measured=[])
    # Findings 1 and 2 should be accepted, 3 and 4 should be dropped
    assert len(findings) == 2
    assert all(f.source == "ai" for f in findings)
    assert any("pytest" in f.evidence for f in findings)
    assert any("Run" in f.evidence for f in findings)
    assert not any("cargo" in f.evidence for f in findings)


# ---------------------------------------------------------------------------
# 3. Element number validation
# ---------------------------------------------------------------------------


def test_site_element_number_validation(monkeypatch, tmp_path):
    el1 = Element(
        number=1,
        selector="button#one",
        tag="button",
        text="One",
        box=Box(x=10, y=10, w=100, h=40),
        name="One",
        meta={"kind": "interactive"},
    )
    img_path = tmp_path / "test.png"
    img_path.write_bytes(b"\x89PNG\r\n\x1a\n")

    snapshot = PageSnapshot(
        url="http://example.local",
        screenshot_path=str(img_path),
        page_width=1280,
        page_height=800,
        elements=[el1],
    )

    mock_response = {
        "enrich": [],
        "new_findings": [
            # Valid element number (exists in snapshot)
            {
                "element_number": 1,
                "rule": "visual-hierarchy",
                "severity": "medium",
                "problem": "Button #1 lacks contrast",
                "why_it_matters": "Low visibility",
                "fix": "Highlight button",
                "evidence": "Observed on element #1",
                "confidence": 0.95,
            },
            # Invalid element number (does NOT exist in snapshot)
            {
                "element_number": 999,
                "rule": "visual-hierarchy",
                "severity": "high",
                "problem": "Non-existent element",
                "why_it_matters": "Invalid",
                "fix": "Fix",
                "evidence": "Does not exist",
                "confidence": 0.95,
            },
        ],
    }

    monkeypatch.setattr("sightline.gemma_review.ask_json", lambda *a, **kw: mock_response)

    results = review_site(snapshot, img_path, measured=[])
    assert len(results) == 1
    assert results[0].element_number == 1
    assert results[0].source == "ai"
    assert results[0].id == "ai-001"


# ---------------------------------------------------------------------------
# 4. None handling (returns measured findings unchanged)
# ---------------------------------------------------------------------------


def test_none_handling_returns_measured_unchanged(monkeypatch, tmp_path):
    img_path = tmp_path / "test.png"
    img_path.write_bytes(b"\x89PNG\r\n\x1a\n")

    snapshot = PageSnapshot(
        url="http://example.local",
        screenshot_path=str(img_path),
        page_width=1280,
        page_height=800,
        elements=[],
    )
    repo = RepoSnapshot(
        url="http://github.com/ex/repo",
        owner="ex",
        name="repo",
        description=None,
        homepage=None,
        default_branch="main",
        files=[],
        truncated=False,
        readme=None,
    )

    measured_site = [
        Finding(
            id="site-001",
            source="measured",
            target="site",
            rule="low-contrast",
            severity="high",
            problem="Contrast issue",
            why_it_matters="Readability",
            fix="Change color",
        )
    ]
    measured_repo = [
        Finding(
            id="repo-001",
            source="measured",
            target="repo",
            rule="no-license",
            severity="high",
            problem="Missing license",
            why_it_matters="Legal clarity",
            fix="Add LICENSE file",
        )
    ]

    # Model call returns None (e.g. network failure)
    monkeypatch.setattr("sightline.gemma_review.ask_json", lambda *a, **kw: None)

    site_res = review_site(snapshot, img_path, measured_site)
    assert site_res == measured_site

    repo_res = review_repo(repo, measured_repo)
    assert repo_res == measured_repo


# ---------------------------------------------------------------------------
# 5. Issue Markdown generation contains all sections
# ---------------------------------------------------------------------------


def test_issue_markdown_generation_sections():
    finding = Finding(
        id="ai-001",
        source="ai",
        target="site",
        rule="visual-hierarchy",
        severity="medium",
        problem="Primary call-to-action button lacks visual contrast against header gradient",
        why_it_matters="Users fail to locate the primary conversion goal quickly.",
        fix="Apply high-contrast dark blue background with white text.",
        fix_snippet="button.cta { background: #1e3a8a; color: #ffffff; }",
        fix_value="#1e3a8a",
        evidence="Element #2 has transparent background and 1px gray border.",
        confidence=0.95,
        element_number=2,
        verified=True,
        verified_note="Verified element #2",
    )

    md = to_issue(finding)
    assert md.startswith("# [MEDIUM]")
    assert "## What's wrong" in md
    assert "Primary call-to-action button lacks visual contrast" in md
    assert "## Evidence" in md
    assert "Element number**: #2" in md
    assert "Element #2 has transparent background" in md
    assert "## Why it matters" in md
    assert "Users fail to locate the primary conversion goal" in md
    assert "## Suggested fix" in md
    assert "button.cta { background: #1e3a8a; color: #ffffff; }" in md
    assert "**Recommended value**: `#1e3a8a`" in md
    assert "## How it was found" in md
    assert "AI analysis via Gemma 4 and SightLine." in md
    assert "## Checklist" in md
    assert "- [ ] Review the proposed fix" in md


# ---------------------------------------------------------------------------
# 6. Merge findings ordering and deduplication
# ---------------------------------------------------------------------------


def test_merge_findings_sorting_and_deduplication():
    f_high_measured = Finding(
        id="site-001",
        source="measured",
        target="site",
        rule="contrast",
        severity="high",
        problem="Low contrast",
        why_it_matters="",
        fix="",
        element_number=1,
        verified=True,
        confidence=1.0,
    )
    f_high_ai_dup = Finding(
        id="ai-001",
        source="ai",
        target="site",
        rule="contrast",
        severity="high",
        problem="Low contrast",
        why_it_matters="",
        fix="",
        element_number=1,
        verified=True,
        confidence=0.9,
    )
    f_med_ai = Finding(
        id="ai-002",
        source="ai",
        target="site",
        rule="hierarchy",
        severity="medium",
        problem="Hierarchy issue",
        why_it_matters="",
        fix="",
        element_number=2,
        verified=True,
        confidence=0.85,
    )
    f_low_ai = Finding(
        id="ai-003",
        source="ai",
        target="site",
        rule="spacing",
        severity="low",
        problem="Spacing issue",
        why_it_matters="",
        fix="",
        element_number=3,
        verified=False,
        confidence=0.7,
    )

    merged = merge_findings([f_high_measured], [f_high_ai_dup, f_low_ai, f_med_ai])
    assert len(merged) == 3
    # Check deduplication on element 1
    assert merged[0].id == "site-001"
    # Order should be high -> medium -> low
    assert [f.severity for f in merged] == ["high", "medium", "low"]


# ---------------------------------------------------------------------------
# 7. Live test: review_repo on sample_repo.json
# ---------------------------------------------------------------------------


@pytest.mark.live
def test_live_review_repo(monkeypatch):
    import os

    from dotenv import load_dotenv

    load_dotenv(override=True)
    if not os.getenv("GEMINI_API_KEY"):
        pytest.skip("GEMINI_API_KEY is not set.")

    monkeypatch.setenv("MOCK", "0")
    monkeypatch.setenv("NO_CACHE", "1")

    fixtures_path = Path("tests/fixtures/sample_repo.json")
    repo_data = json.loads(fixtures_path.read_text(encoding="utf-8"))

    repo = RepoSnapshot(
        url=f"https://github.com/{repo_data['owner']}/{repo_data['name']}",
        owner=repo_data["owner"],
        name=repo_data["name"],
        description=repo_data.get("description"),
        homepage=repo_data.get("homepage"),
        default_branch=repo_data.get("default_branch", "main"),
        files=repo_data.get("files", []),
        truncated=repo_data.get("truncated", False),
        readme=repo_data.get("readme"),
        key_files=repo_data.get("key_files", {}),
    )

    findings = review_repo(repo, measured=[])
    print(f"\n[LIVE REPO REVIEW RESULT]: {len(findings)} findings returned:")
    for f in findings:
        print(f" - [{f.severity.upper()}] {f.rule}: {f.problem} (evidence: {f.evidence!r})")

    assert isinstance(findings, list)
    # Every AI finding that passed validation must have verifiable evidence in the repo
    corpus = normalize_text(repo.readme or "")
    for f in findings:
        if f.source == "ai":
            assert normalize_text(f.evidence) in corpus
