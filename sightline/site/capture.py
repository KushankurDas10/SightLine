"""Browser automation to snapshot pages, take screenshots, and collect DOM elements."""

import ipaddress
import os
import re
import socket
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image
from playwright.sync_api import sync_playwright

from sightline.config import settings
from sightline.models import Box, Element, PageSnapshot


def validate_url(url: str, allow_private: bool | None = None) -> str:
    """Validate that the URL is http/https and does not resolve to disallowed addresses.

    Raises:
        ValueError: If the scheme is invalid, host is missing, or resolves to disallowed IP.
    """
    if allow_private is None:
        allow_private = (
            os.getenv("ALLOW_PRIVATE_URLS", "0").strip().lower() in ("1", "true", "yes")
            or settings.allow_private_urls
        )

    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        raise ValueError(
            f"Invalid URL scheme '{scheme}'. Only http and https URLs are supported."
        )

    hostname = parsed.hostname
    if not hostname:
        raise ValueError(f"Invalid URL '{url}': hostname is missing.")

    if not allow_private:
        try:
            addr_info = socket.getaddrinfo(hostname, None)
        except socket.gaierror as exc:
            raise ValueError(f"Could not resolve hostname '{hostname}': {exc}") from exc

        for entry in addr_info:
            ip_str = entry[4][0]
            try:
                ip = ipaddress.ip_address(ip_str)
            except ValueError:
                continue

            if (
                ip.is_loopback
                or ip.is_private
                or ip.is_link_local
                or ip.is_reserved
                or ip.is_unspecified
            ):
                raise ValueError(
                    f"URL '{url}' resolves to disallowed private/loopback address: {ip_str}"
                )

    return url


DOM_EXTRACTION_SCRIPT = """
() => {
  const elements = [];
  let currentNumber = 1;
  let textCount = 0;

  function isVisible(el) {
    const style = window.getComputedStyle(el);
    if (style.display === 'none' ||
        style.visibility === 'hidden' ||
        parseFloat(style.opacity) === 0) {
      return false;
    }
    const rect = el.getBoundingClientRect();
    return (rect.width > 0 && rect.height > 0) || el.getClientRects().length > 0;
  }

  function getUniqueSelector(el) {
    if (el.id && document.querySelectorAll('#' + CSS.escape(el.id)).length === 1) {
      return '#' + CSS.escape(el.id);
    }
    const path = [];
    let cur = el;
    while (cur && cur.nodeType === Node.ELEMENT_NODE && cur !== document.documentElement) {
      if (cur.id && document.querySelectorAll('#' + CSS.escape(cur.id)).length === 1) {
        path.unshift('#' + CSS.escape(cur.id));
        break;
      }
      const tag = cur.tagName.toLowerCase();
      let sibling = cur;
      let nth = 1;
      while ((sibling = sibling.previousElementSibling)) {
        if (sibling.tagName.toLowerCase() === tag) {
          nth++;
        }
      }
      path.unshift(`${tag}:nth-of-type(${nth})`);
      cur = cur.parentElement;
    }
    return path.join(' > ');
  }

  function resolveBackground(el) {
    let cur = el;
    while (cur && cur.nodeType === Node.ELEMENT_NODE) {
      const bg = window.getComputedStyle(cur).backgroundColor;
      if (bg && bg !== 'rgba(0, 0, 0, 0)' && bg !== 'transparent') {
        return bg;
      }
      cur = cur.parentElement;
    }
    return '#ffffff';
  }

  function computeAccessibleName(el) {
    const labelledby = el.getAttribute('aria-labelledby');
    if (labelledby) {
      const parts = labelledby.trim().split(/\\s+/).map(id => {
        const target = document.getElementById(id);
        return target ? (target.innerText || target.textContent || '').trim() : '';
      }).filter(Boolean);
      if (parts.length > 0) return parts.join(' ');
    }

    const ariaLabel = el.getAttribute('aria-label');
    if (ariaLabel && ariaLabel.trim()) {
      return ariaLabel.trim();
    }

    const tag = el.tagName.toLowerCase();
    if (['input', 'select', 'textarea'].includes(tag)) {
      if (el.id) {
        const label = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
        if (label && label.textContent.trim()) {
          return label.textContent.trim();
        }
      }
      const parentLabel = el.closest('label');
      if (parentLabel && parentLabel.textContent.trim()) {
        return parentLabel.textContent.trim();
      }
      if (tag === 'input' && ['button', 'submit', 'reset'].includes(el.type)) {
        if (el.value && el.value.trim()) {
          return el.value.trim();
        }
      }
      return '';
    }

    const innerImg = el.querySelector('img[alt]');
    if (innerImg && innerImg.getAttribute('alt') && innerImg.getAttribute('alt').trim()) {
      return innerImg.getAttribute('alt').trim();
    }

    const text = (el.innerText || el.textContent || '').trim();
    if (text) {
      return text;
    }

    const title = el.getAttribute('title');
    if (title && title.trim()) {
      return title.trim();
    }

    if (tag === 'img') {
      const alt = el.getAttribute('alt');
      if (alt && alt.trim()) return alt.trim();
    }

    return '';
  }

  function hasDirectText(el) {
    for (const child of el.childNodes) {
      if (child.nodeType === Node.TEXT_NODE && child.textContent.trim().length > 0) {
        return true;
      }
    }
    return false;
  }

  const allElements = document.querySelectorAll('*');
  const scrollX = window.scrollX || window.pageXOffset || 0;
  const scrollY = window.scrollY || window.pageYOffset || 0;
  const interactiveSel = 'a[href], button, input, select, textarea, [role="button"], [tabindex]';

  for (const el of allElements) {
    if (!isVisible(el)) continue;

    const tag = el.tagName.toLowerCase();
    let kind = null;

    const isInteractive = el.matches(interactiveSel);
    const isImage = tag === 'img';
    const isTextTag = el.matches('p, h1, h2, h3, h4, h5, h6, li, span');

    if (isInteractive) {
      kind = 'interactive';
    } else if (isImage) {
      kind = 'image';
    } else if (isTextTag && hasDirectText(el)) {
      const parentEl = el.parentElement;
      const insideInteractive = parentEl && parentEl.closest(interactiveSel);
      if (!insideInteractive && textCount < 200) {
        kind = 'text';
        textCount++;
      }
    }

    if (!kind) continue;

    const rect = el.getBoundingClientRect();
    const box = {
      x: Math.round((rect.left + scrollX) * 10) / 10,
      y: Math.round((rect.top + scrollY) * 10) / 10,
      w: Math.round(rect.width * 10) / 10,
      h: Math.round(rect.height * 10) / 10,
    };

    const style = window.getComputedStyle(el);
    let visibleText = (el.innerText || el.textContent || '').trim().replace(/\\s+/g, ' ');
    if (visibleText.length > 80) {
      visibleText = visibleText.slice(0, 80);
    }

    const accessibleName = computeAccessibleName(el);

    const meta = {
      kind: kind,
      color: style.color,
      background: resolveBackground(el),
      font_px: parseFloat(style.fontSize) || 16.0,
      font_weight: style.fontWeight || '400',
      alt: el.getAttribute('alt') || null,
      role: el.getAttribute('role') || null,
    };

    elements.push({
      number: currentNumber++,
      selector: getUniqueSelector(el),
      tag: tag,
      text: visibleText,
      box: box,
      name: accessibleName,
      meta: meta,
    });
  }

  return {
    elements: elements,
    lang: document.documentElement.lang || null,
    title: document.title || null,
  };
}
"""


def capture(url: str, out_dir: str | Path | None = None) -> PageSnapshot:
    """Capture a webpage snapshot including full-page screenshot and numbered elements."""
    validated_url = validate_url(url)

    out_path = Path(out_dir) if out_dir else settings.out_dir
    out_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_slug = re.sub(r"[^a-zA-Z0-9]+", "_", validated_url).strip("_")[:40]
    screenshot_file = out_path / f"screenshot_{safe_slug}_{timestamp}.png"

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()
        page.set_default_timeout(30000)

        page.goto(validated_url, timeout=30000, wait_until="load")
        page.wait_for_timeout(1000)

        # Full-page screenshot capped at 6000px height
        temp_screenshot = str(screenshot_file)
        page.screenshot(path=temp_screenshot, full_page=True)

        with Image.open(temp_screenshot) as img:
            page_width = img.width
            if img.height > 6000:
                cropped = img.crop((0, 0, img.width, 6000))
                cropped.save(temp_screenshot)
                page_height = 6000
            else:
                page_height = img.height

        raw_data = page.evaluate(DOM_EXTRACTION_SCRIPT)
        browser.close()

    elements = [
        Element(
            number=item["number"],
            selector=item["selector"],
            tag=item["tag"],
            text=item["text"],
            box=Box(
                x=float(item["box"]["x"]),
                y=float(item["box"]["y"]),
                w=float(item["box"]["w"]),
                h=float(item["box"]["h"]),
            ),
            name=item["name"],
            meta=item["meta"],
        )
        for item in raw_data["elements"]
    ]

    return PageSnapshot(
        url=validated_url,
        screenshot_path=str(screenshot_file),
        page_width=page_width,
        page_height=page_height,
        elements=elements,
        lang=raw_data["lang"],
        title=raw_data["title"],
    )


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m sightline.site.capture <url>")
        sys.exit(1)

    target_url = sys.argv[1]
    start_time = time.time()
    snapshot = capture(target_url)
    elapsed = time.time() - start_time
    print(f"Captured {len(snapshot.elements)} elements in {elapsed:.2f}s")
    print(f"Screenshot path: {snapshot.screenshot_path}")
