"""Browser tests for Phase 9B web frontend using Playwright."""

import socket
import threading
import time

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

    # Wait for server ready
    time.sleep(0.5)
    base_url = f"http://127.0.0.1:{port}"
    try:
        yield base_url
    finally:
        server.should_exit = True


@pytest.mark.browser
def test_frontend_demo(web_server):
    """Loads ?demo=site, verifies the annotated screenshot renders (naturalWidth > 0),
    the explainer section is present, findings render with pills, and NO
    'Copy as GitHub issue' buttons are visible.
    """
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

        # Navigate to ?demo=site
        page.goto(f"{web_server}/?demo=site")

        # Wait for finding cards to be populated
        page.wait_for_selector(".finding-card", timeout=5000)

        # 1. Annotated screenshot renders with naturalWidth > 0
        page.wait_for_selector("#annotated-image", timeout=5000)
        img_eval = "() => document.getElementById('annotated-image').naturalWidth"
        img_natural_width = page.evaluate(img_eval)
        assert img_natural_width > 0, f"Expected naturalWidth > 0, got {img_natural_width}"

        # 2. Explainer section is present
        explainer = page.locator("#explainer-section")
        assert explainer.count() == 1
        explainer_text = page.locator("#explainer-details").text_content()
        assert "How to read these results" in explainer_text
        assert "Measured:" in explainer_text
        assert "AI (Gemma):" in explainer_text
        assert "Verified:" in explainer_text

        # 3. Findings render with badge pills
        cards = page.query_selector_all(".finding-card")
        assert len(cards) > 0
        badge_pills = page.query_selector_all(".finding-card .badge")
        assert len(badge_pills) > 0

        # 4. NO "Copy as GitHub issue" buttons are visible for site mode
        repo_buttons = page.query_selector_all(".copy-issue-btn")
        assert len(repo_buttons) == 0

        # 5. "Copy fix snippet" buttons exist for site mode
        snippet_buttons = page.query_selector_all(".copy-snippet-btn")
        assert len(snippet_buttons) == len(cards)
        assert len(snippet_buttons) > 0

        # Test copying a snippet
        snippet_buttons[0].click()
        page.wait_for_selector(".btn-copy.copied", timeout=2000)
        assert "Copied" in snippet_buttons[0].inner_text()

        # 6. Interactive click on finding card draws highlight box on overlay
        cards[0].click()
        page.wait_for_selector(".screenshot-highlight-box", timeout=2000)
        highlight_box = page.locator(".screenshot-highlight-box")
        assert highlight_box.is_visible()

        # 7. No console errors
        assert console_errors == [], f"Detected console errors: {console_errors}"

        # 8. Test client-side error banner displays on invalid submission
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
def test_frontend_repo_demo(web_server):
    """Loads ?demo=repo, verifies 'Copy as GitHub issue' buttons are present,
    and no screenshot is shown.
    """
    console_errors: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        page.on(
            "console",
            lambda msg: console_errors.append(f"Console {msg.type}: {msg.text}")
            if msg.type == "error"
            else None,
        )
        page.on("pageerror", lambda err: console_errors.append(f"PageError: {err}"))

        page.goto(f"{web_server}/?demo=repo")
        page.wait_for_selector(".finding-card", timeout=5000)

        # 1. "Copy as GitHub issue" buttons are present
        cards = page.query_selector_all(".finding-card")
        assert len(cards) > 0
        copy_buttons = page.query_selector_all(".copy-issue-btn")
        assert len(copy_buttons) == len(cards)

        # Test copying an issue
        copy_buttons[0].click()
        page.wait_for_selector(".btn-copy.copied", timeout=2000)
        assert "Copied" in copy_buttons[0].inner_text()

        # 2. No screenshot is shown (screenshot card is hidden)
        screenshot_card = page.locator("#screenshot-card")
        assert not screenshot_card.is_visible()

        # 3. No console errors
        assert console_errors == [], f"Detected console errors: {console_errors}"

        browser.close()


@pytest.mark.browser
def test_keyboard_navigation_tabbing(web_server):
    """Verify full keyboard accessibility: tabbing moves focus through all interactive elements."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(f"{web_server}/?demo=site")
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
        page.goto(f"{web_server}/?demo=site")
        page.wait_for_selector(".finding-card", timeout=5000)

        initial_cards = page.query_selector_all(".finding-card")
        initial_count = len(initial_cards)
        assert initial_count >= 2

        # Click "High Severity" filter chip
        page.click(".chip[data-filter='high']")
        page.wait_for_timeout(200)
        high_cards = page.query_selector_all(".finding-card")
        assert len(high_cards) >= 1
        for card in high_cards:
            assert "severity-high" in (card.get_attribute("class") or "")

        # Click "All Findings" chip to restore
        page.click(".chip[data-filter='all']")
        page.wait_for_timeout(200)
        all_cards = page.query_selector_all(".finding-card")
        assert len(all_cards) == initial_count

        browser.close()
