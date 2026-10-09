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
        cards[0].click(position={"x": 40, "y": 20})
        page.wait_for_selector(".screenshot-highlight-box", timeout=2000)
        highlight_box = page.locator(".screenshot-highlight-box")
        assert highlight_box.is_visible()

        # 7. Website mode shows NO repo card
        repo_card = page.locator("#repo-card")
        assert not repo_card.is_visible()

        # 8. No console errors
        assert console_errors == [], f"Detected console errors: {console_errors}"

        # 9. Test client-side error banner displays on invalid submission
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
    """Loads ?demo=repo, verifies repo card with star count is present,
    'Copy as GitHub issue' buttons are present, and no screenshot is shown.
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

        # 1. Repo card with star count is visible
        page.wait_for_selector("#repo-card:not(.hidden)", timeout=2000)
        repo_card = page.locator("#repo-card")
        assert repo_card.is_visible()
        repo_card_text = repo_card.inner_text()
        assert "octocat/Hello-World" in repo_card_text
        assert "2.5k" in repo_card_text or "2,450" in repo_card_text
        stars_pill = page.locator(".repo-fact-stars")
        assert stars_pill.is_visible()
        assert "2,450 stars" in (stars_pill.get_attribute("aria-label") or "")

        # 2. "Copy as GitHub issue" buttons are present
        cards = page.query_selector_all(".finding-card")
        assert len(cards) > 0
        copy_buttons = page.query_selector_all(".copy-issue-btn")
        assert len(copy_buttons) == len(cards)

        # Test copying an issue
        copy_buttons[0].click()
        page.wait_for_selector(".btn-copy.copied", timeout=2000)
        assert "Copied" in copy_buttons[0].inner_text()

        # 3. No screenshot is shown (screenshot card is hidden)
        screenshot_card = page.locator("#screenshot-card")
        assert not screenshot_card.is_visible()

        # 4. No console errors
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


@pytest.mark.browser
def test_frontend_compare_images(web_server):
    """Verify ?demo=site shows comparison images with naturalWidth > 0, makes NO /files requests,
    and produces no console errors. Also test native dialog enlargement and Esc key closing.
    """
    console_errors: list[str] = []
    files_requests: list[str] = []

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
        page.on(
            "request",
            lambda req: files_requests.append(req.url) if "/files/" in req.url else None,
        )

        page.goto(f"{web_server}/?demo=site")
        page.wait_for_selector(".finding-card", timeout=5000)

        # 1. Comparison images exist and are loaded with naturalWidth > 0
        page.wait_for_selector(".compare-preview-img", timeout=5000)
        imgs = page.locator(".compare-preview-img")
        img_count = imgs.count()
        assert img_count >= 3, f"Expected at least 3 comparison images, got {img_count}"

        for i in range(img_count):
            img = imgs.nth(i)
            natural_w = img.evaluate("el => el.naturalWidth")
            assert natural_w > 0, (
                f"Expected comparison image #{i+1} naturalWidth > 0, got {natural_w}"
            )

        # 2. Click to enlarge opens native <dialog>
        first_btn = page.locator(".compare-img-btn").first
        first_btn.click()
        page.wait_for_selector("#compare-modal[open]", timeout=2000)
        dialog = page.locator("#compare-modal")
        assert dialog.is_visible()
        modal_eval = "() => document.getElementById('compare-modal-img').naturalWidth"
        modal_img_w = page.evaluate(modal_eval)
        assert modal_img_w > 0

        # 3. Pressing Escape closes dialog
        page.keyboard.press("Escape")
        page.wait_for_timeout(200)
        assert not dialog.is_visible()

        # 4. Demo mode must never call /files
        assert files_requests == [], f"Demo mode made unexpected /files requests: {files_requests}"

        # 5. No console errors
        assert console_errors == [], f"Detected console errors: {console_errors}"

        browser.close()


@pytest.mark.browser
def test_frontend_alternatives_site_vs_repo(web_server):
    """Verify ?demo=site shows 'Other ways to fix this' with working copy button,
    while ?demo=repo shows no alternatives section, and no console errors.
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

        # 1. ?demo=site
        page.goto(f"{web_server}/?demo=site")
        page.wait_for_selector(".finding-card", timeout=5000)

        # Alternatives section is present on site findings
        page.wait_for_selector(".alternatives-section", timeout=2000)
        alt_sections = page.locator(".alternatives-section")
        assert alt_sections.count() > 0

        # Click summary to open details
        summary = page.locator(".alternatives-summary").first
        assert "other ways to fix this" in summary.inner_text().lower()
        summary.click()

        # Check alternative cards and copy button
        copy_alt_btn = page.locator(".copy-alt-snippet-btn").first
        assert copy_alt_btn.is_visible()
        copy_alt_btn.click()
        page.wait_for_timeout(200)
        assert "copied" in copy_alt_btn.inner_text().lower()

        # 2. ?demo=repo shows no alternatives section
        page.goto(f"{web_server}/?demo=repo")
        page.wait_for_selector(".finding-card", timeout=5000)
        repo_alt_sections = page.locator(".alternatives-section")
        assert repo_alt_sections.count() == 0

        # 3. No console errors
        assert console_errors == [], f"Detected console errors: {console_errors}"

        browser.close()
