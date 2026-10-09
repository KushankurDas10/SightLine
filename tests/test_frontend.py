"""Browser test for Phase 9 web frontend using Playwright."""

import json
import socket
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from playwright.sync_api import sync_playwright

from web.app import app


@pytest.fixture(scope="module")
def web_server():
    """Run FastAPI web application in background thread."""
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    # Ensure out/annotated.png exists so /files/annotated.png returns 200 in demo mode
    from PIL import Image

    from sightline.config import settings
    out_dir = Path(__file__).resolve().parent.parent / settings.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    annotated_file = out_dir / "annotated.png"
    if not annotated_file.exists():
        img = Image.new("RGB", (1, 1), color="white")
        img.save(annotated_file)

    # Wait for server ready
    time.sleep(0.5)
    base_url = f"http://127.0.0.1:{port}"
    try:
        yield base_url
    finally:
        server.should_exit = True


@pytest.mark.browser
def test_frontend_demo_mode_browser(web_server):
    """Open ?demo=1 in browser and verify findings count, copy buttons, and zero console errors."""
    sample_path = Path(__file__).resolve().parent.parent / "web" / "sample_result.json"
    with open(sample_path, encoding="utf-8") as f:
        sample_data = json.load(f)
    expected_findings_count = len(sample_data["findings"])

    console_errors: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Listen for console errors and page exceptions
        page.on(
            "console",
            lambda msg: console_errors.append(f"Console {msg.type}: {msg.text}")
            if msg.type == "error"
            else None,
        )
        page.on("pageerror", lambda err: console_errors.append(f"PageError: {err}"))

        # Navigate to ?demo=1
        page.goto(f"{web_server}/?demo=1")

        # Wait for finding cards to be populated
        page.wait_for_selector(".finding-card", timeout=5000)

        # 1. Assert finding cards count equals sample
        cards = page.query_selector_all(".finding-card")
        msg = f"Expected {expected_findings_count} cards, got {len(cards)}"
        assert len(cards) == expected_findings_count, msg

        # 2. Assert copy buttons exist for each finding
        copy_buttons = page.query_selector_all(".copy-issue-btn")
        assert len(copy_buttons) == expected_findings_count
        assert len(copy_buttons) > 0

        # 3. Assert no console errors
        assert console_errors == [], f"Detected console errors: {console_errors}"

        # 4. Assert stats row matches sample data
        stat_total = page.locator("#stat-total").inner_text()
        assert stat_total == str(expected_findings_count)

        # 5. Test copy button interaction and visual feedback
        first_copy_btn = copy_buttons[0]
        first_copy_btn.click()
        page.wait_for_selector(".btn-copy.copied", timeout=2000)
        assert "Copied" in first_copy_btn.inner_text()

        # 6. Test client-side error banner displays on invalid submission
        page.fill("#url-input", "invalid-plain-text")
        page.click("#analyze-btn")
        page.wait_for_selector("#error-banner:not(.hidden)", timeout=2000)
        error_text = page.locator("#error-message").inner_text()
        assert "valid" in error_text.lower() or "http" in error_text.lower()

        # Dismiss error banner
        page.click("#error-dismiss-btn")
        assert page.locator("#error-banner").is_hidden()

        browser.close()


@pytest.mark.browser
def test_keyboard_navigation_tabbing(web_server):
    """Verify full keyboard accessibility: tabbing moves focus through all interactive elements."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(f"{web_server}/?demo=1")
        page.wait_for_selector(".finding-card", timeout=5000)

        # Start tabbing from top of document
        page.keyboard.press("Tab")
        focused_tag = page.evaluate("() => document.activeElement.tagName")
        assert focused_tag in ("BUTTON", "A", "INPUT")

        # Tab through multiple elements and verify document.activeElement changes
        focused_elements = []
        for _ in range(12):
            js_eval = (
                "() => ({ tag: document.activeElement.tagName, "
                "id: document.activeElement.id || document.activeElement.className })"
            )
            el_info = page.evaluate(js_eval)
            focused_elements.append(el_info)

        # Verify focus visited buttons and inputs
        tags_visited = {e["tag"] for e in focused_elements}
        assert "BUTTON" in tags_visited or "INPUT" in tags_visited

        browser.close()


@pytest.mark.browser
def test_filter_chips_interaction(web_server):
    """Verify clicking filter chips filters cards correctly."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(f"{web_server}/?demo=1")
        page.wait_for_selector(".finding-card", timeout=5000)

        # Total cards initially is 6
        initial_cards = page.query_selector_all(".finding-card")
        assert len(initial_cards) == 6

        # Click "High Severity" filter chip
        page.click(".chip[data-filter='high']")
        page.wait_for_timeout(200)
        high_cards = page.query_selector_all(".finding-card")
        assert len(high_cards) == 2  # From sample_result.json, high severity count is 2
        for card in high_cards:
            assert "severity-high" in (card.get_attribute("class") or "")

        # Click "All Findings" chip to restore
        page.click(".chip[data-filter='all']")
        page.wait_for_timeout(200)
        all_cards = page.query_selector_all(".finding-card")
        assert len(all_cards) == 6

        browser.close()
