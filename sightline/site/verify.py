"""Browser-based verification of suggested fixes."""

import io
import logging
import re
import time
from pathlib import Path
from typing import Any

from PIL import Image
from playwright.sync_api import sync_playwright

from sightline.config import settings
from sightline.models import Box, Finding, PageSnapshot
from sightline.site.capture import validate_url
from sightline.site.checks import contrast_ratio, is_bold_weight
from sightline.site.marks import compose_comparison

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


def _generate_compare_image(
    page: Any,
    el_handle: Any,
    finding: Finding,
    el_box: Box,
    orig_screenshot: Image.Image | None,
    out_dir: Path,
    sanitized_name: str | None,
    before_ratio: float | None,
    after_ratio: float | None,
    before_w: float,
    before_h: float,
    after_w: float,
    after_h: float,
) -> tuple[str | None, str | None]:
    """Crop Before and After regions, compose comparison image, and save to disk."""
    try:
        if orig_screenshot is None:
            return None, None

        orig_box = finding.box if finding.box is not None else el_box
        if orig_box is None or orig_box.w <= 0 or orig_box.h <= 0:
            return None, None
        if orig_box.y >= 6000 or orig_box.y >= orig_screenshot.height:
            return None, None

        pad = 24.0
        cx = float(orig_box.x - pad)
        cy = float(orig_box.y - pad)
        cw = float(orig_box.w + pad * 2)
        ch = float(orig_box.h + pad * 2)

        # Minimum crop dimensions 160 x 100 px
        if cw < 160.0:
            cx -= (160.0 - cw) / 2.0
            cw = 160.0
        if ch < 100.0:
            cy -= (100.0 - ch) / 2.0
            ch = 100.0

        # Maximum crop dimensions 600 x 300 px
        if cw > 600.0:
            cw = 600.0
        if ch > 300.0:
            ch = 300.0

        page_w = float(orig_screenshot.width)
        page_h = float(min(6000, orig_screenshot.height))

        # Clamp to page bounds
        cx = max(0.0, min(cx, page_w - cw))
        cy = max(0.0, min(cy, page_h - ch))
        cw = min(cw, page_w - cx)
        ch = min(ch, page_h - cy)

        if cw <= 0 or ch <= 0:
            return None, None

        crop_rect = (int(round(cx)), int(round(cy)), int(round(cx + cw)), int(round(cy + ch)))
        before_crop = orig_screenshot.crop(crop_rect)
        rel_bx = float(orig_box.x - cx)
        rel_by = float(orig_box.y - cy)
        rel_bw = float(orig_box.w)
        rel_bh = float(orig_box.h)

        # Re-read element box for after image
        box_js = (
            "(el) => { const r = el.getBoundingClientRect(); "
            "return { x: r.left + window.scrollX, y: r.top + window.scrollY, "
            "w: r.width, h: r.height }; }"
        )
        new_box_data = el_handle.evaluate(box_js)
        new_box = Box(
            x=float(new_box_data.get("x", orig_box.x)),
            y=float(new_box_data.get("y", orig_box.y)),
            w=float(new_box_data.get("w", orig_box.w)),
            h=float(new_box_data.get("h", orig_box.h)),
        )

        if finding.rule == "missing-name":
            # Rule-specific honesty: missing-name changes nothing visible
            after_crop = before_crop.copy()
            rel_ax = rel_bx
            rel_ay = rel_by
            rel_aw = rel_bw
            rel_ah = rel_bh
            name_str = (sanitized_name or "")[:40]
            compare_note = f'Accessible name: None -> "{name_str}"'
        else:
            # Clip screenshot of the same region
            after_bytes = page.screenshot(
                clip={
                    "x": float(int(round(cx))),
                    "y": float(int(round(cy))),
                    "width": float(int(round(cw))),
                    "height": float(int(round(ch))),
                }
            )
            after_crop = Image.open(io.BytesIO(after_bytes)).convert("RGB")
            rel_ax = float(new_box.x - cx)
            rel_ay = float(new_box.y - cy)
            rel_aw = float(new_box.w)
            rel_ah = float(new_box.h)

            if finding.rule == "low-contrast":
                b_ratio_str = f"{before_ratio:.1f}:1" if before_ratio is not None else "1.5:1"
                a_ratio_str = f"{after_ratio:.1f}:1" if after_ratio is not None else "4.5:1"
                compare_note = f"Contrast {b_ratio_str} -> {a_ratio_str}"
            elif finding.rule == "small-target":
                bw_int = int(round(before_w))
                bh_int = int(round(before_h))
                aw_int = int(round(after_w))
                ah_int = int(round(after_h))
                compare_note = f"Target size {bw_int}x{bh_int} px -> {aw_int}x{ah_int} px"
            else:
                compare_note = "Verified fix"

        # Enlarge small crops 3x
        if (orig_box.w <= 48 and orig_box.h <= 48) or (cw <= 200 and ch <= 120):
            scale = 3
            before_crop = before_crop.resize(
                (before_crop.width * scale, before_crop.height * scale),
                resample=Image.Resampling.NEAREST,
            )
            after_crop = after_crop.resize(
                (after_crop.width * scale, after_crop.height * scale),
                resample=Image.Resampling.NEAREST,
            )
            rel_bx *= scale
            rel_by *= scale
            rel_bw *= scale
            rel_bh *= scale
            rel_ax *= scale
            rel_ay *= scale
            rel_aw *= scale
            rel_ah *= scale

        aria_lbl = (
            sanitized_name[:40]
            if finding.rule == "missing-name" and sanitized_name
            else None
        )
        comp_img = compose_comparison(
            before_img=before_crop,
            after_img=after_crop,
            before_box=Box(rel_bx, rel_by, rel_bw, rel_bh),
            after_box=Box(rel_ax, rel_ay, rel_aw, rel_ah),
            rule=finding.rule,
            note=compare_note,
            aria_label=aria_lbl,
        )

        if comp_img is None:
            return None, None

        compare_dir = out_dir / "compare"
        compare_dir.mkdir(parents=True, exist_ok=True)
        out_file = compare_dir / f"{finding.id}.png"
        comp_img.save(out_file)

        job_id = out_dir.name
        compare_url = f"/files/{job_id}/compare/{finding.id}.png"
        return compare_url, compare_note

    except Exception as exc:
        logger.warning("Failed to generate compare image for %s: %s", finding.id, exc)
        return None, None


def verify_fixes(
    url: str,
    snapshot: PageSnapshot,
    findings: list[Finding],
    out_dir: str | Path | None = None,
) -> list[Finding]:
    """Reopen the page once in browser and verify fixes for supported rules.

    Supported rules: 'missing-name', 'low-contrast', 'small-target'.
    Applies fixed code paths, re-runs rule functions, and sets verified=True
    with verified_note='re-checked after applying the fix' on success.
    Generates side-by-side Before/After comparison images for verified fixes.
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

    # Output directory for comparison images
    target_out = (
        Path(out_dir)
        if out_dir
        else (
            Path(snapshot.screenshot_path).parent
            if snapshot.screenshot_path
            else settings.out_dir
        )
    )

    # Open original full screenshot if available
    orig_screenshot: Image.Image | None = None
    if snapshot.screenshot_path and Path(snapshot.screenshot_path).is_file():
        try:
            orig_screenshot = Image.open(snapshot.screenshot_path).convert("RGB")
        except Exception as exc:
            logger.warning("Could not open original screenshot for comparison: %s", exc)

    # Speed limit: verify at most 10 findings
    to_verify = candidate_findings[:10]
    for f in candidate_findings[10:]:
        f.verified = False
        f.verified_note = "verification skipped: exceeded 10 findings limit"
        f.compare_image = None

    start_time = time.perf_counter()
    time_limit = 15.0
    compare_count = 0

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
                    f.compare_image = None
                    continue

                if f.element_number is None or f.element_number not in elements_by_number:
                    f.verified = False
                    f.verified_note = "element not found in snapshot"
                    f.compare_image = None
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
                    f.compare_image = None
                    continue

                try:
                    sanitized_name = None
                    before_ratio = None
                    after_ratio = None
                    before_w, before_h = float(el.box.w), float(el.box.h)
                    after_w, after_h = before_w, before_h

                    if f.rule == "missing-name":
                        sanitized_name = sanitize_aria_label(f.fix_value)
                        if not sanitized_name:
                            f.verified = False
                            f.verified_note = "invalid or empty fix_value for aria-label"
                            f.compare_image = None
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
                            f.compare_image = None

                    elif f.rule == "low-contrast":
                        hex_color = sanitize_hex_color(f.fix_value)
                        if not hex_color:
                            f.verified = False
                            f.verified_note = "invalid fix_value: not a 6-digit hex color"
                            f.compare_image = None
                            continue

                        # Read before facts
                        before_facts = el_handle.evaluate(CONTRAST_FACTS_JS)
                        before_ratio = contrast_ratio(
                            before_facts.get("color"), before_facts.get("background")
                        )

                        # Fixed code path: set style.color
                        el_handle.evaluate("(el, val) => el.style.color = val", hex_color)

                        # Re-collect facts and re-run low-contrast rule
                        facts = el_handle.evaluate(CONTRAST_FACTS_JS)
                        fg = facts.get("color")
                        bg = facts.get("background")
                        after_ratio = contrast_ratio(fg, bg)
                        if after_ratio is not None:
                            font_px = float(facts.get("font_px", 16.0))
                            font_weight = facts.get("font_weight", "400")
                            is_bold = is_bold_weight(font_weight)
                            is_large = font_px >= 24.0 or (font_px >= 18.66 and is_bold)
                            threshold = 3.0 if is_large else 4.5
                            if after_ratio >= threshold:
                                f.verified = True
                                f.verified_note = "re-checked after applying the fix"
                            else:
                                f.verified = False
                                f.verified_note = (
                                    f"contrast ratio {after_ratio:.2f}:1 "
                                    f"still below {threshold:.1f}:1"
                                )
                                f.compare_image = None
                        else:
                            f.verified = False
                            f.verified_note = "unable to determine contrast after fix"
                            f.compare_image = None

                    elif f.rule == "small-target":
                        # Read before box
                        before_box_script = (
                            "(el) => { const r = el.getBoundingClientRect(); "
                            "return { w: r.width, h: r.height }; }"
                        )
                        bbox_pre = el_handle.evaluate(before_box_script)
                        before_w = float(bbox_pre.get("w", el.box.w))
                        before_h = float(bbox_pre.get("h", el.box.h))

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
                        after_w = float(box.get("w", 0.0))
                        after_h = float(box.get("h", 0.0))
                        if after_w >= 24.0 and after_h >= 24.0:
                            f.verified = True
                            f.verified_note = "re-checked after applying the fix"
                        else:
                            f.verified = False
                            f.verified_note = (
                                f"target size {after_w:.1f}x{after_h:.1f}px "
                                f"still below 24x24px"
                            )
                            f.compare_image = None

                    # If verified, generate before & after comparison image
                    if f.verified:
                        if compare_count < 10 and (time.perf_counter() - start_time < time_limit):
                            comp_url, comp_note = _generate_compare_image(
                                page=page,
                                el_handle=el_handle,
                                finding=f,
                                el_box=el.box,
                                orig_screenshot=orig_screenshot,
                                out_dir=target_out,
                                sanitized_name=sanitized_name,
                                before_ratio=before_ratio,
                                after_ratio=after_ratio,
                                before_w=before_w,
                                before_h=before_h,
                                after_w=after_w,
                                after_h=after_h,
                            )
                            f.compare_image = comp_url
                            if comp_note:
                                f.compare_note = comp_note
                            if comp_url:
                                compare_count += 1
                        else:
                            f.compare_image = None
                            if time.perf_counter() - start_time >= time_limit:
                                f.verified_note = (
                                    "re-checked after applying the fix "
                                    "(comparison skipped: timed out)"
                                )

                except Exception as exc:
                    logger.warning("Error verifying finding %s: %s", f.id, exc)
                    f.verified = False
                    f.verified_note = f"error applying or verifying fix: {exc}"
                    f.compare_image = None

            browser.close()

    except Exception as exc:
        logger.warning("Browser verification session failed: %s", exc)

    return findings
