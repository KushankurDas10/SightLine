"""Tests for deterministic site checks and contrast calculation."""

import pytest

from sightline.models import Box, Element, PageSnapshot
from sightline.site.capture import capture
from sightline.site.checks import contrast_ratio, run_all


def test_contrast_ratio_exact_values():
    # Black and white contrast ratio is exactly 21:1
    bw = contrast_ratio("#000000", "#ffffff")
    assert bw == 21.0

    # #777777 on white is about 4.48 (fails normal text threshold of 4.5)
    gray_white = contrast_ratio("#777777", "#ffffff")
    assert gray_white is not None
    assert 4.47 <= gray_white <= 4.49

    # rgb/rgba parsing
    rgb_bw = contrast_ratio("rgb(0, 0, 0)", "rgb(255, 255, 255)")
    assert rgb_bw == 21.0

    # Unknown / transparent backgrounds return None
    assert contrast_ratio("#000000", "transparent") is None
    assert contrast_ratio("#000000", None) is None


def test_hand_built_snapshots_rules():
    # Good base snapshot
    good_element = Element(
        number=1,
        selector="button.save",
        tag="button",
        text="Save",
        box=Box(x=0, y=0, w=100, h=40),
        name="Save",
        meta={
            "kind": "interactive",
            "color": "#ffffff",
            "background": "#000000",
            "font_px": 16.0,
            "font_weight": "400",
        },
    )
    good_snapshot = PageSnapshot(
        url="https://example.com",
        screenshot_path="/tmp/shot.png",
        page_width=1280,
        page_height=800,
        elements=[good_element],
        lang="en",
        title="Valid Title",
    )
    assert run_all(good_snapshot) == []

    # 1. missing-lang and missing-title (page level)
    bad_page = PageSnapshot(
        url="https://example.com",
        screenshot_path="/tmp/shot.png",
        page_width=1280,
        page_height=800,
        elements=[],
        lang=None,
        title="",
    )
    page_findings = run_all(bad_page)
    rules = {f.rule for f in page_findings}
    assert "missing-lang" in rules
    assert "missing-title" in rules
    assert all(f.element_number is None for f in page_findings)

    # 2. missing-name (high)
    nameless_el = Element(
        number=2,
        selector="button.icon",
        tag="button",
        text="",
        box=Box(x=0, y=0, w=30, h=30),
        name="",
        meta={"kind": "interactive"},
    )
    f_name = run_all(
        PageSnapshot("https://ex.com", "", 1280, 800, [nameless_el], lang="en", title="T")
    )
    assert len(f_name) == 1
    assert f_name[0].rule == "missing-name"
    assert f_name[0].severity == "high"
    assert f_name[0].element_number == 2

    # 3. missing-alt (medium) vs decorative alt=""
    img_no_alt = Element(
        number=3,
        selector="img.hero",
        tag="img",
        text="",
        box=Box(x=0, y=0, w=100, h=100),
        name="",
        meta={"kind": "image", "alt": None},
    )
    img_decorative = Element(
        number=4,
        selector="img.dec",
        tag="img",
        text="",
        box=Box(x=0, y=0, w=100, h=100),
        name="",
        meta={"kind": "image", "alt": ""},
    )
    f_alt = run_all(
        PageSnapshot(
            "https://ex.com",
            "",
            1280,
            800,
            [img_no_alt, img_decorative],
            lang="en",
            title="T",
        )
    )
    assert len(f_alt) == 1
    assert f_alt[0].rule == "missing-alt"
    assert f_alt[0].element_number == 3

    # 4. small-target (medium)
    small_el = Element(
        number=5,
        selector="a.tiny",
        tag="a",
        text="x",
        box=Box(x=0, y=0, w=16, h=16),
        name="Close",
        meta={"kind": "interactive"},
    )
    f_target = run_all(
        PageSnapshot("https://ex.com", "", 1280, 800, [small_el], lang="en", title="T")
    )
    assert len(f_target) == 1
    assert f_target[0].rule == "small-target"
    assert f_target[0].severity == "medium"
    assert f_target[0].element_number == 5

    # 5. low-contrast: normal vs large text
    normal_low_contrast = Element(
        number=6,
        selector="p.sub",
        tag="p",
        text="Subtle text",
        box=Box(x=0, y=0, w=200, h=30),
        name="Subtle text",
        meta={
            "kind": "text",
            "color": "#777777",
            "background": "#ffffff",
            "font_px": 16.0,
            "font_weight": "400",
        },
    )
    f_contrast = run_all(
        PageSnapshot(
            "https://ex.com",
            "",
            1280,
            800,
            [normal_low_contrast],
            lang="en",
            title="T",
        )
    )
    assert len(f_contrast) == 1
    assert f_contrast[0].rule == "low-contrast"
    assert f_contrast[0].severity == "medium"

    # Large text with same 4.48 ratio passes threshold 3.0
    large_text = Element(
        number=7,
        selector="h1.head",
        tag="h1",
        text="Large Heading",
        box=Box(x=0, y=0, w=300, h=50),
        name="Large Heading",
        meta={
            "kind": "text",
            "color": "#777777",
            "background": "#ffffff",
            "font_px": 24.0,
            "font_weight": "400",
        },
    )
    assert (
        run_all(PageSnapshot("https://ex.com", "", 1280, 800, [large_text], lang="en", title="T"))
        == []
    )


@pytest.mark.browser
def test_fixture_page_planted_problems(fixtures_server, tmp_path):
    page_url = f"{fixtures_server}/page.html"
    snapshot = capture(page_url, out_dir=tmp_path)
    findings = run_all(snapshot)

    # Exactly the 3 planted problems
    assert len(findings) == 3
    found_rules = {f.rule for f in findings}
    assert found_rules == {"low-contrast", "missing-name", "small-target"}

    # The good button must not be flagged
    good_button = next((el for el in snapshot.elements if el.name == "Save Changes"), None)
    assert good_button is not None
    assert all(f.element_number != good_button.number for f in findings)
