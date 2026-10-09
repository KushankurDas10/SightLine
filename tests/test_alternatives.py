"""Tests for measured and AI alternative fixes (FEATURE C)."""

import re
from dataclasses import asdict

from sightline.gemma_review import _validate_ai_alternative, review_site
from sightline.models import Box, Element, Finding, PageSnapshot
from sightline.site.alternatives import (
    HEX_COLOR_REGEX,
    attach_measured_alternatives,
    generate_measured_alternatives,
)
from sightline.site.checks import contrast_ratio


def test_low_contrast_alternatives_pass_ratio_and_valid_hex():
    """Verify low-contrast alternatives pass WCAG ratio and contain valid 6-digit hex colors."""
    el = Element(
        number=1,
        selector="p.subtext",
        tag="p",
        text="Low contrast paragraph text",
        box=Box(x=10, y=10, w=200, h=20),
        name=None,
        meta={
            "color": "rgb(209, 213, 219)",  # light gray
            "background": "#ffffff",
            "font_px": 16.0,
            "font_weight": "400",
        },
    )
    finding = Finding(
        id="site-001",
        source="measured",
        target="site",
        rule="low-contrast",
        severity="medium",
        problem="Contrast ratio 1.54:1 is below 4.5:1",
        why_it_matters="Hard to read",
        fix="Darken text",
        element_number=1,
    )

    alts = generate_measured_alternatives(finding, el)
    assert len(alts) == 2

    for alt in alts:
        assert alt["source"] == "measured"
        assert alt["check_note"] is not None
        assert "(computed)" in alt["check_note"]
        assert len(alt["label"]) <= 60
        assert len(alt["fix_snippet"]) <= 600

        # Validate hex color in snippet
        match = re.search(r"#(?:[0-9a-fA-F]{6})", alt["fix_snippet"])
        assert match is not None, f"Expected 6-digit hex color in: {alt['fix_snippet']}"
        hex_color = match.group(0)
        assert HEX_COLOR_REGEX.match(hex_color)

        if "color:" in alt["fix_snippet"] and "background-color:" not in alt["fix_snippet"]:
            ratio = contrast_ratio(hex_color, "#ffffff")
            assert ratio is not None
            assert ratio >= 4.5, f"Text color {hex_color} must pass 4.5:1, got {ratio}"
        elif "background-color:" in alt["fix_snippet"]:
            ratio = contrast_ratio("rgb(209, 213, 219)", hex_color)
            assert ratio is not None
            assert ratio >= 4.5, f"Background color {hex_color} must pass 4.5:1, got {ratio}"


def test_small_target_alternatives_mention_real_current_size():
    """Verify small-target alternatives mention the real element size in check_note."""
    el = Element(
        number=2,
        selector="a.tiny",
        tag="a",
        text="x",
        box=Box(x=50, y=50, w=12.0, h=14.0),
        name="Close",
        meta={"kind": "interactive"},
    )
    finding = Finding(
        id="site-002",
        source="measured",
        target="site",
        rule="small-target",
        severity="medium",
        problem="Target size 12x14 is below 24x24",
        why_it_matters="Difficult to tap",
        fix="Increase size",
        element_number=2,
        box=el.box,
    )

    alts = generate_measured_alternatives(finding, el)
    assert len(alts) == 2
    for alt in alts:
        assert alt["source"] == "measured"
        assert alt["check_note"] is not None
        assert "12x14 px" in alt["check_note"]
        assert "target 24x24 px" in alt["check_note"]
        assert "(computed)" in alt["check_note"]


def test_missing_name_sr_only_snippet_present():
    """Verify missing-name alternatives include .sr-only markup and CSS."""
    el = Element(
        number=3,
        selector="button.icon",
        tag="button",
        text="",
        box=Box(x=10, y=10, w=32, h=32),
        name="",
        meta={"kind": "interactive"},
    )
    finding = Finding(
        id="site-003",
        source="measured",
        target="site",
        rule="missing-name",
        severity="high",
        problem="Button has no accessible name",
        why_it_matters="Screen reader silence",
        fix="Add name",
        element_number=3,
    )

    alts = generate_measured_alternatives(finding, el)
    sr_alt = next((a for a in alts if ".sr-only" in a["label"]), None)
    assert sr_alt is not None
    assert '<span class="sr-only">' in sr_alt["fix_snippet"]
    assert ".sr-only {" in sr_alt["fix_snippet"]
    assert "clip: rect(0, 0, 0, 0)" in sr_alt["fix_snippet"]


def test_no_alternative_duplicates_main_fix():
    """Verify alternatives do not duplicate the finding's main fix or fix_value."""
    # 1. low-contrast with fix_value matching closest passing text color
    el = Element(
        number=1,
        selector="p",
        tag="p",
        text="Text",
        box=Box(x=0, y=0, w=100, h=20),
        name=None,
        meta={"color": "#aaaaaa", "background": "#ffffff"},
    )
    finding = Finding(
        id="site-001",
        source="measured",
        target="site",
        rule="low-contrast",
        severity="medium",
        problem="Low contrast",
        why_it_matters="Readability",
        fix="Darken text",
        fix_value="#595959",  # closest passing color
        element_number=1,
    )
    alts = generate_measured_alternatives(finding, el)
    # The option matching #595959 must be omitted
    for alt in alts:
        assert "#595959" not in alt["fix_snippet"]

    # 2. small-target with main fix being 24px min dimensions
    finding_small = Finding(
        id="site-002",
        source="measured",
        target="site",
        rule="small-target",
        severity="medium",
        problem="Small target",
        why_it_matters="Motor accessibility",
        fix="Set min-width: 24px;",
        fix_value="24px",
        element_number=1,
        box=Box(x=0, y=0, w=10, h=10),
    )
    alts_small = generate_measured_alternatives(finding_small, el)
    labels = [a["label"] for a in alts_small]
    assert "Set minimum dimensions" not in labels
    assert any("padding" in lbl.lower() for lbl in labels)
    assert any("pseudo-element" in lbl.lower() for lbl in labels)

    # 3. missing-name with main fix being aria-label
    finding_name = Finding(
        id="site-003",
        source="measured",
        target="site",
        rule="missing-name",
        severity="high",
        problem="Missing name",
        why_it_matters="A11y",
        fix="Add aria-label",
        fix_value="Settings",
        element_number=1,
    )
    alts_name = generate_measured_alternatives(finding_name, el)
    labels_name = [a["label"] for a in alts_name]
    assert "Add aria-label attribute" not in labels_name


def test_ai_alternative_with_script_tag_or_overlong_snippet_dropped():
    """Verify AI alternatives with script tags or snippets >600 chars are dropped."""
    # Script tag in snippet -> dropped
    alt_script = {
        "label": "Inject script",
        "fix": "Add evil tag",
        "fix_snippet": '<script>alert("xss")</script>',
        "tradeoff": "Dangerous",
    }
    assert _validate_ai_alternative(alt_script) is None

    # Script tag in label -> dropped
    alt_script_label = {
        "label": '<script>alert(1)</script>Fix',
        "fix": "Safe fix",
        "fix_snippet": "color: red;",
        "tradeoff": "None",
    }
    assert _validate_ai_alternative(alt_script_label) is None

    # Javascript: URL -> dropped
    alt_js_url = {
        "label": "Click handler",
        "fix": "Use URL",
        "fix_snippet": 'href="javascript:doSomething()"',
        "tradeoff": "None",
    }
    assert _validate_ai_alternative(alt_js_url) is None

    # Snippet > 600 chars -> dropped
    alt_overlong = {
        "label": "Overlong CSS snippet",
        "fix": "Mega CSS fix",
        "fix_snippet": "a" * 601,
        "tradeoff": "Verbose",
    }
    assert _validate_ai_alternative(alt_overlong) is None

    # Valid alternative passes and is sanitized
    alt_valid = {
        "label": "Use CSS border",
        "fix": "Add a 2px high contrast border",
        "fix_snippet": "border: 2px solid #2563eb;",
        "tradeoff": "Higher visibility without changing layout background.",
    }
    validated = _validate_ai_alternative(alt_valid)
    assert validated is not None
    assert validated["source"] == "ai"
    assert validated["label"] == "Use CSS border"
    assert validated["check_note"] == "not browser-verified"


def test_gemma_none_leaves_measured_alternatives_intact(monkeypatch, tmp_path):
    """Verify that when Gemma returns None, measured alternatives remain intact."""
    el = Element(
        number=1,
        selector="p",
        tag="p",
        text="Light text",
        box=Box(x=10, y=10, w=200, h=30),
        name=None,
        meta={"color": "#d1d5db", "background": "#ffffff"},
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
            severity="medium",
            problem="Low contrast",
            why_it_matters="A11y",
            fix="Fix color",
            element_number=1,
        )
    ]

    # Pre-attach measured alternatives
    attach_measured_alternatives(snapshot, measured)
    assert len(measured[0].alternatives) > 0

    # Mock ask_json to return None (e.g. timeout / failure)
    monkeypatch.setattr("sightline.gemma_review.ask_json", lambda *a, **kw: None)

    reviewed = review_site(snapshot, img_path, measured)
    assert len(reviewed) == 1
    assert len(reviewed[0].alternatives) > 0
    assert reviewed[0].alternatives[0]["source"] == "measured"


def test_old_results_without_field_still_load():
    """Verify backwards compatibility: Finding works with default empty alternatives."""
    old_finding = Finding(
        id="site-001",
        source="measured",
        target="site",
        rule="low-contrast",
        severity="medium",
        problem="Low contrast",
        why_it_matters="A11y",
        fix="Fix color",
    )
    assert hasattr(old_finding, "alternatives")
    assert old_finding.alternatives == []

    # Roundtrip asdict serialization
    d = asdict(old_finding)
    assert "alternatives" in d
    assert d["alternatives"] == []
