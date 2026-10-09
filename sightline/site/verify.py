"""Browser-based verification of suggested fixes."""

import logging
import re
import time
from typing import Any

from playwright.sync_api import sync_playwright

from sightline.models import Finding, PageSnapshot
from sightline.site.capture import validate_url
from sightline.site.checks import contrast_ratio, is_bold_weight

logger = logging.getLogger(__name__)

HEX_COLOR_REGEX = re.compile(r"^#[0-9a-fA-F]{6}$")

ACCESSIBLE_NAME_JS = """
(el) => {
  const ariaLabel = el.getAttribute('aria-label');
  if (ariaLabel && ariaLabel.trim()) return ariaLabel.trim();

  const labelledby = el.getAttribute('aria-labelledby');
  if (labelledby) {
    const parts = labelledby.trim().split(/\\s+/).map(id => {
      const target = document.getElementById(id);
      return target ? (target.innerText || target.textContent || '').trim() : '';
    }).filter(Boolean);
    if (parts.length > 0) return parts.join(' ');
  }

  const tag = el.tagName.toLowerCase();
  if (['input', 'select', 'textarea'].includes(tag)) {
    if (el.id) {
      const label = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (label && label.textContent.trim()) return label.textContent.trim();
    }
    const parentLabel = el.closest('label');
    if (parentLabel && parentLabel.textContent.trim()) return parentLabel.textContent.trim();
    if (tag === 'input' && ['button', 'submit', 'reset'].includes(el.type)) {
      if (el.value && el.value.trim()) return el.value.trim();
    }
    return '';
  }

  const innerImg = el.querySelector('img[alt]');
  if (innerImg) {
    const alt = innerImg.getAttribute('alt');
    if (alt && alt.trim()) return alt.trim();
  }

  const text = (el.innerText || el.textContent || '').trim().replace(/\\s+/g, ' ');
  if (text) return text;

  const title = el.getAttribute('title');
  if (title && title.trim()) return title.trim();

  return '';
}
"""

CONTRAST_FACTS_JS = """
(el) => {
  function resolveBackground(node) {
    let cur = node;
    while (cur && cur.nodeType === Node.ELEMENT_NODE) {
      const bg = window.getComputedStyle(cur).backgroundColor;
      if (bg && bg !== 'rgba(0, 0, 0, 0)' && bg !== 'transparent') {
        return bg;
      }
      cur = cur.parentElement;
    }
    return '#ffffff';
  }

  const style = window.getComputedStyle(el);
  return {
    color: style.color,
    background: resolveBackground(el),
    font_px: parseFloat(style.fontSize) || 16.0,
    font_weight: style.fontWeight || '400',
  };
}
"""


def sanitize_aria_label(val: Any) -> str | None:
    """Sanitize fix_value for aria-label: plain text, at most 80 chars."""
    if val is None:
        return None
    s = str(val)
    # Strip HTML tags
    s = re.sub(r"<[^>]*>", "", s)
    # Strip non-printable / control chars and newlines
    s = re.sub(r"[\r\n\t\x00-\x1f\x7f-\x9f]+", " ", s)
    # Collapse multiple whitespaces
    s = " ".join(s.split()).strip()
    if not s:
        return None
    return s[:80].strip()


def sanitize_hex_color(val: Any) -> str | None:
    """Validate fix_value for style.color matching ^#[0-9a-fA-F]{6}$."""
    if val is None:
        return None
    s = str(val).strip()
    if HEX_COLOR_REGEX.match(s):
        return s
    return None


def verify_fixes(
    url: str,
    snapshot: PageSnapshot,
    findings: list[Finding],
) -> list[Finding]:
    """Reopen the page once in browser and verify fixes for supported rules.

    Supported rules: 'missing-name', 'low-contrast', 'small-target'.
    Applies fixed code paths, re-runs rule functions, and sets verified=True
    with verified_note='re-checked after applying the fix' on success.
    Enforces speed limits: at most 10 findings verified, 15 seconds max runtime.
    Never raises an exception on invalid inputs or browser failures.
    """
    supported_rules = {"missing-name", "low-contrast", "small-target"}
    candidate_findings = [f for f in findings if f.rule in supported_rules]

    if not candidate_findings:
        return findings

    try:
        validated_url = validate_url(url)
    except Exception as exc:
        logger.warning("URL validation failed during verify_fixes: %s", exc)
        return findings

    elements_by_number = {el.number: el for el in snapshot.elements}

    # Speed limit: verify at most 10 findings
    to_verify = candidate_findings[:10]
    for f in candidate_findings[10:]:
        f.verified = False
        f.verified_note = "verification skipped: exceeded 10 findings limit"

    start_time = time.perf_counter()
    time_limit = 15.0

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1280, "height": 800})
            page = context.new_page()
            page.set_default_timeout(10000)

            # Reopen the page once for all fixes
            page.goto(validated_url, timeout=10000, wait_until="load")
            page.wait_for_timeout(300)

            for f in to_verify:
                # Check 15-second speed limit cap
                if time.perf_counter() - start_time >= time_limit:
                    f.verified = False
                    f.verified_note = "verification skipped: timed out"
                    continue

                if f.element_number is None or f.element_number not in elements_by_number:
                    f.verified = False
                    f.verified_note = "element not found in snapshot"
                    continue

                el = elements_by_number[f.element_number]
                selector = el.selector

                try:
                    el_handle = page.query_selector(selector)
                except Exception as exc:
                    logger.debug("query_selector error on %s: %s", selector, exc)
                    el_handle = None

                if el_handle is None:
                    f.verified = False
                    f.verified_note = "element not found on page"
                    continue

                try:
                    if f.rule == "missing-name":
                        sanitized_name = sanitize_aria_label(f.fix_value)
                        if not sanitized_name:
                            f.verified = False
                            f.verified_note = "invalid or empty fix_value for aria-label"
                            continue

                        # Fixed code path: set aria-label attribute
                        el_handle.evaluate(
                            "(el, val) => el.setAttribute('aria-label', val)", sanitized_name
                        )

                        # Re-collect facts and re-run missing-name rule
                        re_name = el_handle.evaluate(ACCESSIBLE_NAME_JS)
                        if re_name and str(re_name).strip():
                            f.verified = True
                            f.verified_note = "re-checked after applying the fix"
                        else:
                            f.verified = False
                            f.verified_note = "accessible name still empty after fix"

                    elif f.rule == "low-contrast":
                        hex_color = sanitize_hex_color(f.fix_value)
                        if not hex_color:
                            f.verified = False
                            f.verified_note = "invalid fix_value: not a 6-digit hex color"
                            continue

                        # Fixed code path: set style.color
                        el_handle.evaluate("(el, val) => el.style.color = val", hex_color)

                        # Re-collect facts and re-run low-contrast rule
                        facts = el_handle.evaluate(CONTRAST_FACTS_JS)
                        fg = facts.get("color")
                        bg = facts.get("background")
                        ratio = contrast_ratio(fg, bg)
                        if ratio is not None:
                            font_px = float(facts.get("font_px", 16.0))
                            font_weight = facts.get("font_weight", "400")
                            is_bold = is_bold_weight(font_weight)
                            is_large = font_px >= 24.0 or (font_px >= 18.66 and is_bold)
                            threshold = 3.0 if is_large else 4.5
                            if ratio >= threshold:
                                f.verified = True
                                f.verified_note = "re-checked after applying the fix"
                            else:
                                f.verified = False
                                f.verified_note = (
                                    f"contrast ratio {ratio:.2f}:1 still below {threshold:.1f}:1"
                                )
                        else:
                            f.verified = False
                            f.verified_note = "unable to determine contrast after fix"

                    elif f.rule == "small-target":
                        # Fixed code path: set min-width and min-height to 24px
                        el_handle.evaluate(
                            """(el) => {
                                el.style.minWidth = '24px';
                                el.style.minHeight = '24px';
                                if (window.getComputedStyle(el).display === 'inline') {
                                    el.style.display = 'inline-block';
                                }
                            }"""
                        )

                        # Re-collect facts and re-run small-target rule
                        box_script = (
                            "(el) => { const r = el.getBoundingClientRect(); "
                            "return { w: r.width, h: r.height }; }"
                        )
                        box = el_handle.evaluate(box_script)
                        bw = float(box.get("w", 0.0))
                        bh = float(box.get("h", 0.0))
                        if bw >= 24.0 and bh >= 24.0:
                            f.verified = True
                            f.verified_note = "re-checked after applying the fix"
                        else:
                            f.verified = False
                            f.verified_note = f"target size {bw:.1f}x{bh:.1f}px still below 24x24px"

                except Exception as exc:
                    logger.warning("Error verifying finding %s: %s", f.id, exc)
                    f.verified = False
                    f.verified_note = f"error applying or verifying fix: {exc}"

            browser.close()

    except Exception as exc:
        logger.warning("Browser verification session failed: %s", exc)

    return findings
