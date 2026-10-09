"""Tests for sightline.site.verify fix verification."""

import re

import pytest
from PIL import Image

from sightline.models import Finding, PageSnapshot
from sightline.site.capture import capture
from sightline.site.checks import run_all as run_site_checks
from sightline.site.verify import sanitize_aria_label, sanitize_hex_color, verify_fixes

# ---------------------------------------------------------------------------
# 1. Sanitizer unit tests
# ---------------------------------------------------------------------------


def test_sanitize_aria_label():
    """Verify aria-label sanitizing: plain text, stripped tags, control chars, max 80."""
    assert sanitize_aria_label("Submit form") == "Submit form"
    assert sanitize_aria_label("  Submit   form \t\r\n ") == "Submit form"

    # HTML tags stripped
    assert sanitize_aria_label("<b>Save</b> changes") == "Save changes"
    assert sanitize_aria_label("<svg><path/></svg>Settings") == "Settings"

    # Long string truncated to 80 chars
    long_label = "A" * 100
    sanitized = sanitize_aria_label(long_label)
    assert sanitized is not None
    assert len(sanitized) == 80
    assert sanitized == "A" * 80

    # None, empty, whitespace only
    assert sanitize_aria_label(None) is None
    assert sanitize_aria_label("") is None
    assert sanitize_aria_label("   ") is None
    assert sanitize_aria_label("<script></script>") is None


def test_sanitize_hex_color():
    """Verify hex color validation against ^#[0-9a-fA-F]{6}$."""
    # Valid 6-digit hex
    assert sanitize_hex_color("#1e3a8a") == "#1e3a8a"
    assert sanitize_hex_color("#FFFFFF") == "#FFFFFF"
    assert sanitize_hex_color("  #000000  ") == "#000000"
    assert sanitize_hex_color("#abcdef") == "#abcdef"

    # Invalid hex colors
    assert sanitize_hex_color("#fff") is None
    assert sanitize_hex_color("1e3a8a") is None
    assert sanitize_hex_color("blue") is None
    assert sanitize_hex_color("rgb(0, 0, 0)") is None
    assert sanitize_hex_color("#1234567") is None
    assert sanitize_hex_color("#12345g") is None
    assert sanitize_hex_color(None) is None
    assert sanitize_hex_color("") is None


# ---------------------------------------------------------------------------
# 2. Limit and error resilience unit tests
# ---------------------------------------------------------------------------


def test_verify_fixes_no_candidates():
    """Verify that when no supported rule findings exist, verify_fixes returns immediately."""
    snapshot = PageSnapshot(
        url="https://example.com",
        screenshot_path="",
        page_width=1280,
        page_height=800,
        elements=[],
        lang=None,
        title=None,
    )
    findings = [
        Finding(
            id="site-001",
            source="measured",
            target="site",
            rule="missing-lang",
            severity="medium",
            problem="Missing lang",
            why_it_matters="A11y",
            fix="Add lang",
        )
    ]
    result = verify_fixes("https://example.com", snapshot, findings)
    assert result == findings
    assert result[0].verified is False


def test_verify_fixes_invalid_url_never_raises():
    """Verify that invalid URL (e.g. private loopback rejected by default) never raises."""
    snapshot = PageSnapshot(
        url="http://127.0.0.1:9999",
        screenshot_path="",
        page_width=1280,
        page_height=800,
        elements=[],
    )
    findings = [
        Finding(
            id="site-001",
            source="measured",
            target="site",
            rule="small-target",
            severity="medium",
            problem="Small target",
            why_it_matters="A11y",
            fix="Expand size",
            element_number=1,
        )
    ]
    # Without ALLOW_PRIVATE_URLS, 127.0.0.1 is rejected by validate_url
    result = verify_fixes("http://127.0.0.1:9999", snapshot, findings)
    assert len(result) == 1
    assert result[0].verified is False


def test_verify_fixes_exceeds_10_limit(monkeypatch):
    """Verify that only at most 10 findings are verified and the rest are marked skipped."""
    snapshot = PageSnapshot(
        url="https://example.com",
        screenshot_path="",
        page_width=1280,
        page_height=800,
        elements=[],
    )
    findings = [
        Finding(
            id=f"site-{i:03d}",
            source="measured",
            target="site",
            rule="small-target",
            severity="medium",
            problem="Small target",
            why_it_matters="A11y",
            fix="Expand size",
            element_number=i,
        )
        for i in range(1, 15)
    ]

    # Monkeypatch validate_url to succeed
    monkeypatch.setattr("sightline.site.verify.validate_url", lambda u: u)

    # Monkeypatch sync_playwright to avoid real browser launch in unit test
    class DummyBrowser:
        def new_context(self, **kw):
            return self

        def new_page(self):
            return self

        def set_default_timeout(self, *a):
            pass

        def goto(self, *a, **kw):
            pass

        def wait_for_timeout(self, *a):
            pass

        def query_selector(self, *a):
            return None

        def close(self):
            pass

    class DummyPlaywright:
        chromium = DummyBrowser()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

    monkeypatch.setattr("sightline.site.verify.sync_playwright", lambda: DummyPlaywright())

    result = verify_fixes("https://example.com", snapshot, findings)
    assert len(result) == 14
    # Findings 11 to 14 must have the exceeded 10 limit note
    for f in result[10:]:
        assert f.verified is False
        assert "exceeded 10 findings limit" in f.verified_note


# ---------------------------------------------------------------------------
# 3. Browser-based verification tests on page.html fixture
# ---------------------------------------------------------------------------


@pytest.mark.browser
def test_verify_fixes_page_html_all_three_planted_problems(fixtures_server, tmp_path):
    """Verify all 3 planted problems on page.html are verified after applying sensible fixes,
    generate comparison images that open with Pillow, show real before/after notes,
    and unverified findings have no compare_image.
    """
    page_url = f"{fixtures_server}/page.html"
    snapshot = capture(page_url, out_dir=tmp_path)
    findings = run_site_checks(snapshot)

    # Find the 3 planted problems
    low_contrast = next(f for f in findings if f.rule == "low-contrast")
    missing_name = next(f for f in findings if f.rule == "missing-name")
    small_target = next(f for f in findings if f.rule == "small-target")

    # Supply sensible fix values
    low_contrast.fix_value = "#111827"  # dark gray meeting WCAG AA contrast on white
    missing_name.fix_value = "Settings Action"
    small_target.fix_value = "24px"

    # Add an unverified finding (invalid fix value)
    unverified = Finding(
        id="site-unverified-099",
        source="measured",
        target="site",
        rule="missing-name",
        severity="high",
        problem="Icon button with invalid fix",
        why_it_matters="A11y",
        fix="Add name",
        fix_value="   ",
        element_number=missing_name.element_number,
    )
    findings.append(unverified)

    updated_findings = verify_fixes(page_url, snapshot, findings, out_dir=tmp_path)

    for f in updated_findings:
        if f.id == "site-unverified-099":
            assert f.verified is False
            assert f.compare_image is None
        elif f.rule in ("low-contrast", "missing-name", "small-target"):
            assert f.verified is True
            assert f.verified_note == "re-checked after applying the fix"
            assert f.compare_image is not None
            assert f.compare_image.startswith("/files/")
            assert f.compare_image.endswith(f"compare/{f.id}.png")

            # compare_image file exists on disk and opens with Pillow
            img_file = tmp_path / "compare" / f"{f.id}.png"
            assert img_file.is_file(), f"Comparison image {img_file} should exist"
            with Image.open(img_file) as img:
                assert img.width > 0
                assert img.height > 0

            # compare_note shows the real before and after values
            assert f.compare_note is not None
            if f.rule == "small-target":
                match = re.search(r"->\s*(\d+)x(\d+)\s*px", f.compare_note)
                assert match is not None, f"Expected -> WxH in {f.compare_note}"
                after_w = int(match.group(1))
                assert after_w >= 24, f"Expected after width >= 24, got {after_w}"
            elif f.rule == "low-contrast":
                assert "Contrast" in f.compare_note
                assert "->" in f.compare_note
            elif f.rule == "missing-name":
                assert "Accessible name" in f.compare_note
                assert "Settings Action" in f.compare_note


@pytest.mark.browser
def test_verify_fixes_invalid_hex_does_not_verify_or_crash(fixtures_server, tmp_path):
    """Verify that an invalid fix_value (not a hex color) is not verified and does not crash."""
    page_url = f"{fixtures_server}/page.html"
    snapshot = capture(page_url, out_dir=tmp_path)
    findings = run_site_checks(snapshot)

    low_contrast = next(f for f in findings if f.rule == "low-contrast")
    # Invalid fix_value: not a 6-digit hex color
    low_contrast.fix_value = "light-blue"

    missing_name = next(f for f in findings if f.rule == "missing-name")
    # Invalid fix_value: empty
    missing_name.fix_value = "   "

    updated = verify_fixes(page_url, snapshot, findings, out_dir=tmp_path)
    assert len(updated) > 0

    assert low_contrast.verified is False
    assert "not a 6-digit hex color" in low_contrast.verified_note
    assert low_contrast.compare_image is None

    assert missing_name.verified is False
    assert "invalid or empty fix_value" in missing_name.verified_note
    assert missing_name.compare_image is None
