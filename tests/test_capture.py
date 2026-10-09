"""Tests for webpage capture and URL validation."""

import socket
from pathlib import Path

import pytest

from sightline.site.capture import capture, validate_url


def test_validate_url_rejects_invalid_schemes():
    with pytest.raises(ValueError, match="Only http and https URLs are supported"):
        validate_url("javascript:alert(1)")

    with pytest.raises(ValueError, match="Only http and https URLs are supported"):
        validate_url("file:///etc/passwd")


def test_validate_url_rejects_private_and_loopback():
    with pytest.raises(ValueError, match="disallowed private/loopback address"):
        validate_url("http://127.0.0.1:8000", allow_private=False)

    with pytest.raises(ValueError, match="disallowed private/loopback address"):
        validate_url("http://10.0.0.1/dashboard", allow_private=False)


def test_validate_url_accepts_public_address(monkeypatch):
    def fake_getaddrinfo(host, port):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    result = validate_url("https://example.com", allow_private=False)
    assert result == "https://example.com"


@pytest.mark.browser
def test_capture_fixture_page(fixtures_server, tmp_path):
    page_url = f"{fixtures_server}/page.html"
    snapshot = capture(page_url, out_dir=tmp_path)

    assert snapshot.url == page_url
    assert snapshot.lang == "en"
    assert snapshot.title == "SightLine Test Fixture Page"
    assert Path(snapshot.screenshot_path).exists()
    assert snapshot.page_width == 1280
    assert snapshot.page_height > 0

    # Elements found and numbered sequentially from 1
    assert len(snapshot.elements) >= 4
    numbers = [el.number for el in snapshot.elements]
    assert numbers == list(range(1, len(snapshot.elements) + 1))

    # Find the planted elements
    tiny_link = next(
        (
            el
            for el in snapshot.elements
            if "planted-tiny-link" in el.selector or el.text == "x"
        ),
        None,
    )
    assert tiny_link is not None
    assert 7.0 <= tiny_link.box.w <= 14.0
    assert 7.0 <= tiny_link.box.h <= 14.0

    icon_button = next(
        (
            el
            for el in snapshot.elements
            if "planted-icon-button" in el.selector or (el.tag == "button" and el.name == "")
        ),
        None,
    )
    assert icon_button is not None
    assert icon_button.name == ""

    good_button = next(
        (
            el
            for el in snapshot.elements
            if "good-button" in el.selector or el.text == "Save Changes"
        ),
        None,
    )
    assert good_button is not None
    assert good_button.name == "Save Changes"
