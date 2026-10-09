"""Deterministic alternative fixes for website accessibility findings."""

import colorsys
import re
from typing import Any

from sightline.models import Element, Finding, PageSnapshot
from sightline.site.checks import contrast_ratio, is_bold_weight, parse_color

HEX_COLOR_REGEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    """Format RGB integer channels as a 6-digit hex string."""
    return f"#{min(255, max(0, r)):02x}{min(255, max(0, g)):02x}{min(255, max(0, b)):02x}"


def _hls_to_hex(h: float, lum: float, s: float) -> str:
    """Convert HLS floats to a 6-digit hex string."""
    r, g, b = colorsys.hls_to_rgb(h, min(1.0, max(0.0, lum)), min(1.0, max(0.0, s)))
    return _rgb_to_hex(round(r * 255), round(g * 255), round(b * 255))


def find_closest_passing_color(
    fg_color: str,
    bg_color: str,
    target_ratio: float,
) -> tuple[str, float]:
    """Find closest passing text color by adjusting lightness while preserving hue."""
    fg_rgb = parse_color(fg_color) or (0, 0, 0)
    bg_rgb = parse_color(bg_color) or (255, 255, 255)
    bg_clean = _rgb_to_hex(*bg_rgb)

    h, lum, s = colorsys.rgb_to_hls(fg_rgb[0] / 255.0, fg_rgb[1] / 255.0, fg_rgb[2] / 255.0)

    # Determine primary direction to adjust lightness
    r_down = contrast_ratio(_hls_to_hex(h, max(0.0, lum - 0.05), s), bg_clean) or 1.0
    r_up = contrast_ratio(_hls_to_hex(h, min(1.0, lum + 0.05), s), bg_clean) or 1.0

    directions = [-0.01, 0.01] if r_down >= r_up else [0.01, -0.01]

    best_hex = _hls_to_hex(h, lum, s)
    best_ratio = contrast_ratio(best_hex, bg_clean) or 1.0
    if best_ratio >= target_ratio:
        return best_hex, best_ratio

    for step in directions:
        curr_l = lum
        while 0.0 <= curr_l <= 1.0:
            curr_l += step
            cand_hex = _hls_to_hex(h, curr_l, s)
            cand_ratio = contrast_ratio(cand_hex, bg_clean) or 1.0
            if cand_ratio >= target_ratio:
                return cand_hex, cand_ratio

    # Fallback to black or white if hue adjustment couldn't reach target ratio
    r_black = contrast_ratio("#000000", bg_clean) or 1.0
    r_white = contrast_ratio("#ffffff", bg_clean) or 1.0
    if r_black >= r_white:
        return "#000000", r_black
    return "#ffffff", r_white


def find_passing_background(
    fg_color: str,
    bg_color: str,
    target_ratio: float,
) -> tuple[str, float]:
    """Find passing background color by adjusting background lightness while preserving hue."""
    fg_rgb = parse_color(fg_color) or (0, 0, 0)
    bg_rgb = parse_color(bg_color) or (255, 255, 255)
    fg_clean = _rgb_to_hex(*fg_rgb)

    h, lum, s = colorsys.rgb_to_hls(bg_rgb[0] / 255.0, bg_rgb[1] / 255.0, bg_rgb[2] / 255.0)

    r_down = contrast_ratio(fg_clean, _hls_to_hex(h, max(0.0, lum - 0.05), s)) or 1.0
    r_up = contrast_ratio(fg_clean, _hls_to_hex(h, min(1.0, lum + 0.05), s)) or 1.0

    directions = [-0.01, 0.01] if r_down >= r_up else [0.01, -0.01]

    for step in directions:
        curr_l = lum
        while 0.0 <= curr_l <= 1.0:
            curr_l += step
            cand_hex = _hls_to_hex(h, curr_l, s)
            cand_ratio = contrast_ratio(fg_clean, cand_hex) or 1.0
            if cand_ratio >= target_ratio:
                return cand_hex, cand_ratio

    r_white = contrast_ratio(fg_clean, "#ffffff") or 1.0
    r_black = contrast_ratio(fg_clean, "#000000") or 1.0
    if r_white >= r_black:
        return "#ffffff", r_white
    return "#000000", r_black


def find_maximum_contrast_color(bg_color: str) -> tuple[str, float]:
    """Return black or white, whichever has the higher contrast against the background."""
    bg_rgb = parse_color(bg_color) or (255, 255, 255)
    bg_clean = _rgb_to_hex(*bg_rgb)
    r_black = contrast_ratio("#000000", bg_clean) or 1.0
    r_white = contrast_ratio("#ffffff", bg_clean) or 1.0
    if r_black >= r_white:
        return "#000000", r_black
    return "#ffffff", r_white


def find_adjacent_text_element(
    element: Element | None,
    snapshot: PageSnapshot | None,
) -> tuple[str, str] | None:
    """Find a visible text element right next to the given element."""
    if not element or not element.box or not snapshot or not snapshot.elements:
        return None

    el_cx = element.box.x + element.box.w / 2.0
    el_cy = element.box.y + element.box.h / 2.0
    candidates: list[tuple[float, Element]] = []

    for cand in snapshot.elements:
        if cand.number == element.number or not cand.text or not cand.text.strip():
            continue
        if not cand.box:
            continue
        cand_cx = cand.box.x + cand.box.w / 2.0
        cand_cy = cand.box.y + cand.box.h / 2.0
        dist = ((cand_cx - el_cx) ** 2 + (cand_cy - el_cy) ** 2) ** 0.5
        # Adjacent: center within 150 CSS pixels
        if dist <= 150.0:
            candidates.append((dist, cand))

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[0])
    best_cand = candidates[0][1]

    target_id: str | None = None
    if best_cand.meta and best_cand.meta.get("id"):
        target_id = str(best_cand.meta["id"])
    elif best_cand.selector and "#" in best_cand.selector:
        m = re.search(r"#([a-zA-Z0-9_\-]+)", best_cand.selector)
        if m:
            target_id = m.group(1)

    if not target_id:
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", best_cand.text.strip().lower())[:20].strip("-")
        target_id = f"{slug or 'adjacent'}-label"

    return target_id, best_cand.text.strip()


def generate_measured_alternatives(
    finding: Finding,
    element: Element | None,
    snapshot: PageSnapshot | None = None,
) -> list[dict[str, Any]]:
    """Generate 1 or 2 deterministic measured alternative fixes for a finding."""
    rule = finding.rule
    results: list[dict[str, Any]] = []

    # 1. low-contrast
    if rule == "low-contrast":
        fg_color = (
            element.meta.get("color")
            if element and element.meta
            else "rgb(209, 213, 219)"
        )
        bg_color = (
            element.meta.get("background")
            if element and element.meta
            else "#ffffff"
        )
        font_px = float(element.meta.get("font_px", 16.0)) if element and element.meta else 16.0
        font_weight = (
            element.meta.get("font_weight", "400")
            if element and element.meta
            else "400"
        )
        is_large = font_px >= 24.0 or (font_px >= 18.66 and is_bold_weight(font_weight))
        target_ratio = 3.0 if is_large else 4.5

        c1_hex, c1_ratio = find_closest_passing_color(fg_color, bg_color, target_ratio)
        c2_hex, c2_ratio = find_passing_background(fg_color, bg_color, target_ratio)
        c3_hex, c3_ratio = find_maximum_contrast_color(bg_color)

        alt1 = {
            "label": "Closest passing color",
            "description": "Keep hue and adjust text lightness to satisfy WCAG AA contrast.",
            "fix_snippet": f"color: {c1_hex};",
            "tradeoff": "Preserves brand hue, but alters text lightness.",
            "source": "measured",
            "check_note": f"contrast {c1_ratio:.1f}:1 (passes AA) (computed)",
        }
        alt2 = {
            "label": "Change the background instead",
            "description": "Keep text color and adjust background lightness to pass contrast.",
            "fix_snippet": f"background-color: {c2_hex};",
            "tradeoff": "Leaves text color untouched, but alters container background.",
            "source": "measured",
            "check_note": f"contrast {c2_ratio:.1f}:1 (passes AA) (computed)",
        }
        alt3 = {
            "label": "Maximum contrast",
            "description": (
                f"Use {'black' if c3_hex == '#000000' else 'white'} text for highest readability."
            ),
            "fix_snippet": f"color: {c3_hex};",
            "tradeoff": "Guarantees maximum legibility, but replaces custom text color.",
            "source": "measured",
            "check_note": f"contrast {c3_ratio:.1f}:1 (passes AA) (computed)",
        }

        # Offer two alternatives that do not equal the main fix_value
        main_val = (finding.fix_value or "").strip().lower()
        if c1_hex.lower() == main_val:
            results = [alt2, alt3]
        elif c2_hex.lower() == main_val:
            results = [alt1, alt3]
        elif c3_hex.lower() == main_val:
            results = [alt1, alt2]
        else:
            results = [alt1, alt2]

    # 2. small-target
    elif rule == "small-target":
        w = (
            element.box.w
            if element and element.box
            else (finding.box.w if finding.box else 10.0)
        )
        h = (
            element.box.h
            if element and element.box
            else (finding.box.h if finding.box else 10.0)
        )
        check_note = f"Current {int(round(w))}x{int(round(h))} px -> target 24x24 px (computed)"

        alt1 = {
            "label": "Set minimum dimensions",
            "description": "Enforce WCAG 2.2 target size minimum with CSS min-width/min-height.",
            "fix_snippet": "min-width: 24px;\nmin-height: 24px;",
            "tradeoff": "Simple and robust, but may alter layout if container is tightly packed.",
            "source": "measured",
            "check_note": check_note,
        }

        pad_x = max(0, int(round((24.0 - w) / 2.0)))
        pad_y = max(0, int(round((24.0 - h) / 2.0)))
        alt2 = {
            "label": "Expand padding with inline-flex",
            "description": "Increase touch target by adding padding and centered alignment.",
            "fix_snippet": (
                f"display: inline-flex;\nalign-items: center;\njustify-content: center;\n"
                f"padding: {pad_y}px {pad_x}px;"
            ),
            "tradeoff": "Preserves inner icon proportions, but increases outer spacing.",
            "source": "measured",
            "check_note": check_note,
        }

        alt3 = {
            "label": "Invisible pseudo-element hit area",
            "description": "Expand clickable area with an invisible ::after pseudo-element.",
            "fix_snippet": (
                "position: relative;\n&::after {\n"
                "  content: '';\n  position: absolute;\n  top: 50%;\n  left: 50%;\n"
                "  transform: translate(-50%, -50%);\n  min-width: 24px;\n  min-height: 24px;\n"
                "  width: 100%;\n  height: 100%;\n}"
            ),
            "tradeoff": (
                "Zero layout shift, but pseudo-elements may overlap nearby links."
            ),
            "source": "measured",
            "check_note": check_note,
        }

        main_val = (finding.fix_value or "").lower()
        main_snip = (finding.fix_snippet or "").lower()
        main_fix = (finding.fix or "").lower()
        is_min_dim_main = "24px" in main_val or "min-width" in main_snip or "min-width" in main_fix

        if is_min_dim_main:
            results = [alt2, alt3]
        else:
            results = [alt1, alt2]

    # 3. missing-name
    elif rule == "missing-name":
        raw_name = (
            finding.fix_value
            or (element.name.strip() if element and element.name else "Action")
        )
        label_text = re.sub(r"<[^>]*>", "", str(raw_name))
        label_text = re.sub(r"[\r\n\t]+", " ", label_text).strip() or "Action"
        if len(label_text) > 40:
            label_text = label_text[:40]

        alt1 = {
            "label": "Add aria-label attribute",
            "description": f"Provide accessible name directly with aria-label='{label_text}'.",
            "fix_snippet": f'aria-label="{label_text}"',
            "tradeoff": "Direct and clean fix, but invisible to sighted users.",
            "source": "measured",
            "check_note": "not browser-verified",
        }

        tag = element.tag.lower() if element and element.tag else "button"
        sr_snippet = (
            f"<{tag}>\n  <span class=\"sr-only\">{label_text}</span>\n</{tag}>\n\n"
            "/* CSS */\n.sr-only {\n  position: absolute;\n  width: 1px;\n  height: 1px;\n"
            "  padding: 0;\n  margin: -1px;\n  overflow: hidden;\n"
            "  clip: rect(0, 0, 0, 0);\n  white-space: nowrap;\n  border: 0;\n}"
        )
        alt2 = {
            "label": "Screen reader only text (.sr-only)",
            "description": "Embed visually hidden text using standard utility CSS.",
            "fix_snippet": sr_snippet,
            "tradeoff": (
                "Better compatibility with translation and legacy tools, but requires extra markup."
            ),
            "source": "measured",
            "check_note": "not browser-verified",
        }

        adj = find_adjacent_text_element(element, snapshot) if element and snapshot else None
        alt3 = None
        if adj is not None:
            target_id, target_text = adj
            alt3 = {
                "label": "Reference adjacent text with aria-labelledby",
                "description": f"Reference element #{target_id} using aria-labelledby.",
                "fix_snippet": (
                    f'aria-labelledby="{target_id}"\n'
                    f'<!-- On visible text: id="{target_id}" -->'
                ),
                "tradeoff": (
                    "Avoids duplicate copy, but requires unique id on neighboring element."
                ),
                "source": "measured",
                "check_note": "not browser-verified",
            }

        main_val = (finding.fix_value or "").lower()
        main_snip = (finding.fix_snippet or "").lower()
        main_fix = (finding.fix or "").lower()
        is_aria_label_main = (
            bool(finding.fix_value) or "aria-label" in main_snip or "aria-label" in main_fix
        )

        if is_aria_label_main:
            results = [alt2, alt3] if alt3 is not None else [alt2]
        else:
            results = [alt1, alt3] if alt3 is not None else [alt1, alt2]

    # 4. missing-alt
    elif rule == "missing-alt":
        alt_val = (finding.fix_value or "").strip() or "Descriptive image caption"
        alt1 = {
            "label": "Descriptive alt text",
            "description": "Add a meaningful text description of the image content or purpose.",
            "fix_snippet": f'alt="{alt_val}"',
            "tradeoff": "Essential when the image conveys meaningful information to users.",
            "source": "measured",
            "check_note": "not browser-verified",
        }
        alt2 = {
            "label": "Mark as decorative with alt=''",
            "description": "Set empty alt attribute so screen readers completely skip the image.",
            "fix_snippet": 'alt=""',
            "tradeoff": (
                "Use if purely decorative; do not use if image conveys content."
            ),
            "source": "measured",
            "check_note": "not browser-verified",
        }
        main_snip = (finding.fix_snippet or "").lower()
        if 'alt=""' in main_snip:
            results = [alt1]
        else:
            results = [alt1, alt2]

    # Sanitize length and character limits for all generated alternatives
    sanitized_results: list[dict[str, Any]] = []
    for item in results:
        label = str(item.get("label", ""))[:60]
        desc = str(item.get("description", ""))
        snippet = str(item.get("fix_snippet", ""))[:600]
        tradeoff = str(item.get("tradeoff", ""))
        check_note = item.get("check_note")
        sanitized_results.append({
            "label": label,
            "description": desc,
            "fix_snippet": snippet,
            "tradeoff": tradeoff,
            "source": "measured",
            "check_note": check_note,
        })

    return sanitized_results


def attach_measured_alternatives(
    snapshot: PageSnapshot,
    findings: list[Finding],
) -> list[Finding]:
    """Attach measured alternative fixes to website findings."""
    elements_by_number = {el.number: el for el in snapshot.elements}
    for f in findings:
        if f.target != "site":
            continue
        # Skip if finding already has measured alternatives
        has_measured = any(a.get("source") == "measured" for a in f.alternatives)
        if has_measured:
            continue
        el = elements_by_number.get(f.element_number) if f.element_number is not None else None
        measured_alts = generate_measured_alternatives(f, el, snapshot)
        if measured_alts:
            # Combine measured alternatives first, preserving any AI alternatives
            ai_alts = [a for a in f.alternatives if a.get("source") != "measured"]
            f.alternatives = measured_alts + ai_alts
    return findings
