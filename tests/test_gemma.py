"""Tests for sightline.gemma module."""

import io
import os
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PIL import Image

from sightline import gemma
from sightline.gemma import ask_json, parse_json_loose

# ---------------------------------------------------------------------------
# 1. parse_json_loose tests
# ---------------------------------------------------------------------------


def test_parse_json_loose_clean():
    assert parse_json_loose('{"status": "ok", "count": 42}') == {"status": "ok", "count": 42}
    assert parse_json_loose('[1, "two", 3]') == [1, "two", 3]


def test_parse_json_loose_fences():
    fenced_json = """```json
    {
        "findings": [
            {"element_number": 1, "rule": "contrast"}
        ]
    }
    ```"""
    result = parse_json_loose(fenced_json)
    assert result == {"findings": [{"element_number": 1, "rule": "contrast"}]}

    fenced_no_lang = """```
    ["apple", "banana"]
    ```"""
    assert parse_json_loose(fenced_no_lang) == ["apple", "banana"]


def test_parse_json_loose_extra_text():
    conversational = """Here is the UX review you requested:
```json
{
  "notes": ["Looks good"],
  "score": 8
}
```
Let me know if you need any adjustments!"""
    result = parse_json_loose(conversational)
    assert result == {"notes": ["Looks good"], "score": 8}

    no_fences_surrounded = (
        'Pre-text observations: {"rule": "visual-hierarchy"} trailing remarks.'
    )
    assert parse_json_loose(no_fences_surrounded) == {"rule": "visual-hierarchy"}


def test_parse_json_loose_invalid():
    assert parse_json_loose("") is None
    assert parse_json_loose(None) is None
    assert parse_json_loose("This is purely english text with no JSON.") is None
    assert parse_json_loose("{incomplete: json,") is None
    assert parse_json_loose("42") is None


# ---------------------------------------------------------------------------
# 2. Mock mode tests
# ---------------------------------------------------------------------------


def test_mock_mode_site_and_repo(monkeypatch):
    monkeypatch.setenv("MOCK", "1")
    site_result = ask_json("site_review", "Auditing webpage")
    assert site_result is not None
    assert "findings" in site_result
    assert isinstance(site_result["findings"], list)

    repo_result = ask_json("repo_review", "Auditing repository")
    assert repo_result is not None
    assert "summary" in repo_result

    nonexistent = ask_json("nonexistent_kind", "Prompt")
    assert nonexistent is None


# ---------------------------------------------------------------------------
# 3. Cache hit & monkeypatch client tests
# ---------------------------------------------------------------------------


def test_cache_hit_monkeypatch_client(monkeypatch, tmp_path):
    monkeypatch.setenv("MOCK", "0")
    monkeypatch.setenv("NO_CACHE", "0")
    monkeypatch.setenv("GEMINI_API_KEY", "dummy-key")

    # Point repo cache to tmp_path
    monkeypatch.setattr(gemma, "CACHE_DIR", tmp_path / ".cache" / "gemma")

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = SimpleNamespace(
        text='{"data": "cached_response"}'
    )
    monkeypatch.setattr(gemma, "get_client", lambda *args, **kwargs: mock_client)

    prompt = "Test caching prompt"
    img_data = b"sample_bytes_123"

    # First call: cache miss, calls client
    res1 = ask_json("custom", prompt, image_bytes=img_data)
    assert res1 == {"data": "cached_response"}
    assert mock_client.models.generate_content.call_count == 1

    # Second call: cache hit, does not call client
    res2 = ask_json("custom", prompt, image_bytes=img_data)
    assert res2 == {"data": "cached_response"}
    assert mock_client.models.generate_content.call_count == 1

    # Call with NO_CACHE=1: bypasses cache, calls client again
    monkeypatch.setenv("NO_CACHE", "1")
    res3 = ask_json("custom", prompt, image_bytes=img_data)
    assert res3 == {"data": "cached_response"}
    assert mock_client.models.generate_content.call_count == 2


# ---------------------------------------------------------------------------
# 4. Error and retry tests
# ---------------------------------------------------------------------------


def test_retry_on_parse_failure(monkeypatch, tmp_path):
    monkeypatch.setenv("MOCK", "0")
    monkeypatch.setenv("NO_CACHE", "1")
    monkeypatch.setenv("GEMINI_API_KEY", "dummy-key")

    mock_client = MagicMock()
    # First call returns malformed text, second call returns valid JSON
    mock_client.models.generate_content.side_effect = [
        SimpleNamespace(text="Sorry, here is some non-json output"),
        SimpleNamespace(text='{"success_after_retry": true}'),
    ]
    monkeypatch.setattr(gemma, "get_client", lambda *args, **kwargs: mock_client)

    res = ask_json("retry_test", "Generate JSON")
    assert res == {"success_after_retry": True}
    assert mock_client.models.generate_content.call_count == 2


def test_api_error_returns_none(monkeypatch):
    monkeypatch.setenv("MOCK", "0")
    monkeypatch.setenv("GEMINI_API_KEY", "dummy-key")

    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = RuntimeError("Rate limit exceeded or timeout")
    monkeypatch.setattr(gemma, "get_client", lambda *args, **kwargs: mock_client)

    result = ask_json("error_test", "Prompt that triggers API error")
    assert result is None


# ---------------------------------------------------------------------------
# 5. Live test: real reply with small PNG
# ---------------------------------------------------------------------------


@pytest.mark.live
def test_gemma_live_png_description(monkeypatch):
    from dotenv import load_dotenv

    from sightline.config import REPO_ROOT

    load_dotenv(REPO_ROOT / ".env", override=True)
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        pytest.skip("GEMINI_API_KEY is not set in environment or .env; cannot run live test.")

    monkeypatch.setenv("MOCK", "0")
    monkeypatch.setenv("NO_CACHE", "1")

    # Generate a small 64x64 solid blue PNG
    img = Image.new("RGB", (64, 64), color="blue")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    png_bytes = buf.getvalue()

    prompt = (
        "Describe this image in one concise sentence. "
        "Return a JSON object with a single key 'description'."
    )
    result = ask_json(kind="image_desc", prompt=prompt, image_bytes=png_bytes)
    print(f"\n[LIVE GEMMA RESPONSE]: {result}")
    assert result is not None
    assert isinstance(result, dict)
    assert "description" in result
