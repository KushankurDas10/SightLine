"""Tests for sightline.site.marks annotation and badge marking."""

from pathlib import Path

from PIL import Image

from sightline.models import Box, Element, Finding, PageSnapshot
from sightline.site.marks import (
    DEFAULT_MARK_COLOR,
    SEVERITY_COLORS,
    annotate,
    compose_comparison,
    mark_elements,
)


def test_mark_elements_crop_and_borders(tmp_path):
    # 1. Generate a blank white PNG with height > 1800
    blank_w, blank_h = 1000, 2500
    blank_img = Image.new("RGB", (blank_w, blank_h), color=(255, 255, 255))
    blank_path = tmp_path / "blank_source.png"
    blank_img.save(blank_path)

    # 2. Hand-made snapshot with interactive and non-interactive elements
    el_interactive = Element(
        number=1,
        selector="button#action",
        tag="button",
        text="Submit",
        box=Box(x=100, y=100, w=200, h=50),
        name="Submit",
        meta={"kind": "interactive"},
    )
    el_text = Element(
        number=2,
        selector="p.description",
        tag="p",
        text="Some description",
        box=Box(x=100, y=300, w=200, h=50),
        name="",
        meta={"kind": "text"},
    )
    el_overflow = Element(
        number=3,
        selector="a#footer-link",
        tag="a",
        text="Footer",
        box=Box(x=100, y=2100, w=200, h=50),
        name="Footer",
        meta={"kind": "interactive"},
    )

    snapshot = PageSnapshot(
        url="http://example.local/test",
        screenshot_path=str(blank_path),
        page_width=blank_w,
        page_height=blank_h,
        elements=[el_interactive, el_text, el_overflow],
    )

    out_file = tmp_path / "marked.png"
    result_path = mark_elements(snapshot, out_file, max_height=1800)

    # Assert output exists
    assert Path(result_path).exists()

    result_img = Image.open(result_path)
    # Assert height is cropped to at most 1800
    assert result_img.height <= 1800
    assert result_img.height == 1800
    assert result_img.width == blank_w

    # Assert pixels along box border of interactive element differ from white background
    # Top border of el_interactive is around y=100, between x=100 and x=300
    border_pixel = result_img.getpixel((200, 100))
    assert border_pixel != (255, 255, 255)
    assert border_pixel == DEFAULT_MARK_COLOR

    # Assert text element was NOT marked: border at y=300 should remain white
    text_pixel = result_img.getpixel((200, 300))
    assert text_pixel == (255, 255, 255)


def test_mark_elements_short_page(tmp_path):
    # If the page is already shorter than max_height, its height is preserved
    short_img = Image.new("RGB", (800, 600), color=(255, 255, 255))
    short_path = tmp_path / "short_source.png"
    short_img.save(short_path)

    snapshot = PageSnapshot(
        url="http://example.local/short",
        screenshot_path=str(short_path),
        page_width=800,
        page_height=600,
        elements=[],
    )

    out_file = tmp_path / "short_marked.png"
    mark_elements(snapshot, out_file, max_height=1800)

    res = Image.open(out_file)
    assert res.height == 600
    assert res.height <= 1800


def test_annotate_findings_by_severity(tmp_path):
    blank_w, blank_h = 1000, 2000
    blank_img = Image.new("RGB", (blank_w, blank_h), color=(255, 255, 255))
    blank_path = tmp_path / "annotate_source.png"
    blank_img.save(blank_path)

    el1 = Element(
        number=1,
        selector="button#btn1",
        tag="button",
        text="Button 1",
        box=Box(x=50, y=150, w=150, h=40),
        name="Button 1",
    )
    el2 = Element(
        number=2,
        selector="a#link2",
        tag="a",
        text="Link 2",
        box=Box(x=50, y=350, w=150, h=40),
        name="Link 2",
    )

    snapshot = PageSnapshot(
        url="http://example.local/annotate",
        screenshot_path=str(blank_path),
        page_width=blank_w,
        page_height=blank_h,
        elements=[el1, el2],
    )

    findings = [
        Finding(
            id="finding-1",
            source="measured",
            target="site",
            rule="color-contrast",
            severity="high",
            problem="Low contrast",
            why_it_matters="Hard to see",
            fix="Increase contrast",
            element_number=1,
        ),
        Finding(
            id="finding-2",
            source="measured",
            target="site",
            rule="target-size",
            severity="low",
            problem="Small tap target",
            why_it_matters="Hard to tap",
            fix="Make bigger",
            element_number=2,
        ),
        Finding(
            id="finding-3",
            source="measured",
            target="site",
            rule="missing-title",
            severity="medium",
            problem="Missing title",
            why_it_matters="Page accessibility",
            fix="Add title",
            element_number=None,  # Page-level finding
            box=None,
        ),
    ]

    out_file = tmp_path / "annotated.png"
    annotate(snapshot, findings, out_file)

    assert out_file.exists()
    annotated_img = Image.open(out_file)

    # Full screenshot preserved, not cropped
    assert annotated_img.height == blank_h

    # Element 1 has high severity color along its border
    el1_border_pixel = annotated_img.getpixel((100, 150))
    assert el1_border_pixel == SEVERITY_COLORS["high"]

    # Element 2 has low severity color along its border
    el2_border_pixel = annotated_img.getpixel((100, 350))
    assert el2_border_pixel == SEVERITY_COLORS["low"]

    # Other areas remain untouched
    assert annotated_img.getpixel((500, 500)) == (255, 255, 255)


def test_compose_comparison_size_and_pixel_colors():
    """Verify compose_comparison returns expected dimensions with red pixels on left and green."""
    before_img = Image.new("RGB", (200, 120), color=(255, 255, 255))
    after_img = Image.new("RGB", (200, 120), color=(255, 255, 255))
    before_box = Box(20, 20, 50, 40)
    after_box = Box(20, 20, 60, 50)

    composed = compose_comparison(
        before_img=before_img,
        after_img=after_img,
        before_box=before_box,
        after_box=after_box,
        rule="small-target",
        note="Target size 10x10 px -> 24x24 px",
    )

    assert composed is not None
    # panel_w = 200, divider_w = 2, total_w = 402; panel_h = 120, header_h = 28, caption_h = 32
    assert composed.size == (402, 180)

    # Check for red pixels on left half (panel_w = 200)
    left_half = composed.crop((0, 0, 200, composed.height))
    left_pixels = list(left_half.getdata())
    has_red = any(r > 180 and g < 60 and b < 60 for (r, g, b) in left_pixels)
    assert has_red, "Expected red pixels on left half of comparison image"

    # Check for green pixels on right half (panel_w + divider_w = 202 to 402)
    right_half = composed.crop((202, 0, 402, composed.height))
    right_pixels = list(right_half.getdata())
    has_green = any(g > 140 and g > r + 40 and g > b + 40 for (r, g, b) in right_pixels)
    assert has_green, "Expected green pixels on right half of comparison image"


def test_compose_comparison_box_outside_or_zero_size_returns_none():
    """Verify box outside the image or zero size returns None without raising."""
    before_img = Image.new("RGB", (200, 120), color=(255, 255, 255))
    after_img = Image.new("RGB", (200, 120), color=(255, 255, 255))

    b_ok = Box(10, 10, 30, 30)

    # Zero width / zero height
    assert compose_comparison(before_img, after_img, Box(10, 10, 0, 30), b_ok, "rule") is None
    assert compose_comparison(before_img, after_img, b_ok, Box(10, 10, 30, 0), "rule") is None

    # Negative width / height
    assert compose_comparison(before_img, after_img, Box(10, 10, -5, 30), b_ok, "rule") is None

    # Box outside image bounds
    assert compose_comparison(before_img, after_img, Box(300, 300, 20, 20), b_ok, "rule") is None
    assert compose_comparison(before_img, after_img, b_ok, Box(500, 50, 30, 30), "rule") is None

    # None boxes or None images
    assert compose_comparison(before_img, after_img, None, b_ok, "rule") is None
    assert compose_comparison(None, after_img, b_ok, b_ok, "rule") is None
