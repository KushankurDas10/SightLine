"""Measured deterministic accessibility checks for web pages."""

import re
from typing import Any

from sightline.models import Finding, PageSnapshot


def parse_color(color_str: str | None) -> tuple[int, int, int] | None:
    """Parse hex, rgb(), or rgba() string into an (R, G, B) tuple.

    Returns None if color is transparent, invalid, or unknown.
    """
    if not color_str or not isinstance(color_str, str):
        return None

    s = color_str.strip().lower()
    if s in ("transparent", "none", "inherit", "initial", "unset"):
        return None

    # Hex formats: #rgb, #rgba, #rrggbb, #rrggbbaa
    if s.startswith("#"):
        hex_digits = s[1:]
        if len(hex_digits) == 3:
            return (
                int(hex_digits[0] * 2, 16),
                int(hex_digits[1] * 2, 16),
                int(hex_digits[2] * 2, 16),
            )
        if len(hex_digits) == 4:
            alpha = int(hex_digits[3] * 2, 16) / 255.0
            if alpha == 0:
                return None
            return (
                int(hex_digits[0] * 2, 16),
                int(hex_digits[1] * 2, 16),
                int(hex_digits[2] * 2, 16),
            )
        if len(hex_digits) == 6:
            return (
                int(hex_digits[0:2], 16),
                int(hex_digits[2:4], 16),
                int(hex_digits[4:6], 16),
            )
        if len(hex_digits) == 8:
            alpha = int(hex_digits[6:8], 16) / 255.0
            if alpha == 0:
                return None
            return (
                int(hex_digits[0:2], 16),
                int(hex_digits[2:4], 16),
                int(hex_digits[4:6], 16),
            )
        return None

    # rgb(...) or rgba(...)
    rgb_pattern = (
        r"^rgba?\s*\(\s*(\d{1,3})\s*[, ]\s*(\d{1,3})\s*[, ]\s*(\d{1,3})"
        r"(?:\s*[,/]\s*([\d.]+))?\s*\)$"
    )
    match = re.match(rgb_pattern, s)
    if match:
        r, g, b = int(match.group(1)), int(match.group(2)), int(match.group(3))
        alpha_str = match.group(4)
        if alpha_str is not None:
            try:
                alpha = float(alpha_str)
                if alpha == 0:
                    return None
            except ValueError:
                pass
        return (min(max(r, 0), 255), min(max(g, 0), 255), min(max(b, 0), 255))

    return None


def relative_luminance(rgb: tuple[int, int, int]) -> float:
    """Calculate WCAG relative luminance for an sRGB tuple."""

    def channel_luminance(val: int) -> float:
        c = val / 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = rgb
    return (
        0.2126 * channel_luminance(r)
        + 0.7152 * channel_luminance(g)
        + 0.0722 * channel_luminance(b)
    )


def contrast_ratio(fg: str | None, bg: str | None) -> float | None:
    """Calculate the contrast ratio between foreground and background color strings."""
    fg_rgb = parse_color(fg)
    bg_rgb = parse_color(bg)
    if fg_rgb is None or bg_rgb is None:
        return None

    l1 = relative_luminance(fg_rgb)
    l2 = relative_luminance(bg_rgb)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return round((lighter + 0.05) / (darker + 0.05), 2)


def is_bold_weight(weight: Any) -> bool:
    """Return True if the CSS font-weight represents bold text."""
    if weight is None:
        return False
    w_str = str(weight).strip().lower()
    if w_str in ("bold", "bolder"):
        return True
    try:
        return int(w_str) >= 700
    except ValueError:
        return False


def run_all(snapshot: PageSnapshot) -> list[Finding]:
    """Run all measured accessibility checks over a PageSnapshot."""
    findings: list[Finding] = []
    finding_counter = 1

    def make_id() -> str:
        nonlocal finding_counter
        fid = f"site-{finding_counter:03d}"
        finding_counter += 1
        return fid

    # Page-level checks
    if not snapshot.lang or not snapshot.lang.strip():
        findings.append(
            Finding(
                id=make_id(),
                source="measured",
                target="site",
                rule="missing-lang",
                severity="medium",
                problem="The page <html> element is missing a lang attribute.",
                why_it_matters=(
                    "A declared language ensures screen readers pronounce words correctly "
                    "and enables translation tools."
                ),
                fix="",
                evidence="Page snapshot does not specify a lang attribute",
                confidence=1.0,
                element_number=None,
                box=None,
            )
        )

    if not snapshot.title or not snapshot.title.strip():
        findings.append(
            Finding(
                id=make_id(),
                source="measured",
                target="site",
                rule="missing-title",
                severity="medium",
                problem="The document is missing a title.",
                why_it_matters=(
                    "The page title is the first thing announced by screen readers and "
                    "helps users orient themselves across open tabs."
                ),
                fix="",
                evidence="Document title is empty or not provided",
                confidence=1.0,
                element_number=None,
                box=None,
            )
        )

    # Element-level checks
    for el in snapshot.elements:
        kind = el.meta.get("kind", "")

        # 1. missing-name (high): interactive element with empty accessible name
        if kind == "interactive":
            if not el.name or not el.name.strip():
                findings.append(
                    Finding(
                        id=make_id(),
                        source="measured",
                        target="site",
                        rule="missing-name",
                        severity="high",
                        problem=f"Interactive <{el.tag}> element has no accessible name.",
                        why_it_matters=(
                            "Screen readers announce interactive controls by their accessible "
                            "name; without one, users cannot determine its function."
                        ),
                        fix="",
                        evidence=(
                            f"Element #{el.number} <{el.tag}> has an empty accessible name"
                        ),
                        confidence=1.0,
                        element_number=el.number,
                        box=el.box,
                    )
                )

        # 2. missing-alt (medium): img with no alt attribute (alt="" is fine)
        if el.tag.lower() == "img" or kind == "image":
            if el.meta.get("alt") is None:
                findings.append(
                    Finding(
                        id=make_id(),
                        source="measured",
                        target="site",
                        rule="missing-alt",
                        severity="medium",
                        problem=f"Image element <{el.tag}> is missing an alt attribute.",
                        why_it_matters=(
                            "Screen readers rely on alternative text to describe images to blind "
                            "or low-vision users."
                        ),
                        fix="",
                        evidence=f"Element #{el.number} <img> does not have an alt attribute",
                        confidence=1.0,
                        element_number=el.number,
                        box=el.box,
                    )
                )

        # 3. small-target (medium): interactive box smaller than 24x24 CSS px
        if kind == "interactive":
            if el.box and (el.box.w < 24.0 or el.box.h < 24.0):
                findings.append(
                    Finding(
                        id=make_id(),
                        source="measured",
                        target="site",
                        rule="small-target",
                        severity="medium",
                        problem=(
                            f"Interactive target is smaller than 24x24 CSS pixels "
                            f"({el.box.w:.1f}x{el.box.h:.1f}px)."
                        ),
                        why_it_matters=(
                            "Small touch and click targets are difficult to activate accurately, "
                            "especially on touchscreens or for users with motor impairments."
                        ),
                        fix="",
                        evidence=(
                            f"Target size {el.box.w:.1f}x{el.box.h:.1f}px is below WCAG 2.2 "
                            "minimum 24x24px"
                        ),
                        confidence=1.0,
                        element_number=el.number,
                        box=el.box,
                    )
                )

        # 4. low-contrast (high if ratio < 3, else medium): text contrast check
        if el.text and el.text.strip():
            fg_color = el.meta.get("color")
            bg_color = el.meta.get("background")
            ratio = contrast_ratio(fg_color, bg_color)
            if ratio is not None:
                font_px = float(el.meta.get("font_px", 16.0))
                font_weight = el.meta.get("font_weight", "400")
                is_large = font_px >= 24.0 or (font_px >= 18.66 and is_bold_weight(font_weight))
                threshold = 3.0 if is_large else 4.5

                if ratio < threshold:
                    severity = "high" if ratio < 3.0 else "medium"
                    findings.append(
                        Finding(
                            id=make_id(),
                            source="measured",
                            target="site",
                            rule="low-contrast",
                            severity=severity,
                            problem=(
                                f"Text contrast ratio {ratio:.2f}:1 is below required minimum of "
                                f"{threshold:.1f}:1."
                            ),
                            why_it_matters=(
                                "Insufficient contrast makes content hard or impossible to read "
                                "for people with low vision or in bright viewing environments."
                            ),
                            fix="",
                            evidence=(
                                f"contrast {ratio:.2f}:1 for {fg_color} on {bg_color}"
                            ),
                            confidence=1.0,
                            element_number=el.number,
                            box=el.box,
                        )
                    )

    return findings
