"""Gemma model interface via the Gemini API (google-genai)."""

import hashlib
import json
import logging
import os
import re
from typing import Any

from google import genai
from google.genai import types

from sightline.config import REPO_ROOT, settings

logger = logging.getLogger(__name__)

CACHE_DIR = REPO_ROOT / ".cache" / "gemma"


def parse_json_loose(text: str | None) -> dict[str, Any] | list[Any] | None:
    """Parse JSON from model response text, stripping markdown code fences or extra text."""
    if not text or not isinstance(text, str):
        return None

    cleaned = text.strip()

    # 1. Direct JSON parse
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, (dict, list)):
            return parsed
    except Exception:
        pass

    # 2. Extract content between markdown code fences ```json ... ``` or ``` ... ```
    fence_matches = re.findall(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned, re.IGNORECASE)
    for match in fence_matches:
        try:
            parsed = json.loads(match.strip())
            if isinstance(parsed, (dict, list)):
                return parsed
        except Exception:
            pass

    # 3. Extract outermost balanced or sliceable JSON object { ... } or array [ ... ]
    first_brace = cleaned.find("{")
    first_bracket = cleaned.find("[")

    start = -1
    if first_brace != -1 and first_bracket != -1:
        start = min(first_brace, first_bracket)
    elif first_brace != -1:
        start = first_brace
    elif first_bracket != -1:
        start = first_bracket

    if start != -1:
        last_brace = cleaned.rfind("}")
        last_bracket = cleaned.rfind("]")
        end = max(last_brace, last_bracket)
        if end > start:
            candidate = cleaned[start : end + 1].strip()
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, (dict, list)):
                    return parsed
            except Exception:
                pass

    return None


def _is_mock_mode() -> bool:
    """Check if mock mode is explicitly enabled."""
    val = os.getenv("MOCK")
    if val is not None:
        return val.strip().lower() in ("1", "true", "yes")
    return settings.mock


def _is_no_cache() -> bool:
    """Check if caching is disabled via NO_CACHE=1."""
    return os.getenv("NO_CACHE", "0").strip().lower() in ("1", "true", "yes")


def _compute_cache_key(model: str, prompt: str, image_bytes: bytes | None) -> str:
    """Compute sha256 hash for cache key."""
    hasher = hashlib.sha256()
    hasher.update((model + prompt).encode("utf-8"))
    if image_bytes:
        hasher.update(image_bytes)
    return hasher.hexdigest()


def _read_cache(cache_key: str) -> dict[str, Any] | list[Any] | None:
    """Read cached JSON if present."""
    cache_file = CACHE_DIR / f"{cache_key}.json"
    if cache_file.exists():
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            if isinstance(data, (dict, list)):
                return data
        except Exception as exc:
            logger.warning("Failed to read cache file %s: %s", cache_file, exc)
    return None


def _write_cache(cache_key: str, data: dict[str, Any] | list[Any]) -> None:
    """Write parsed JSON to disk cache."""
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_file = CACHE_DIR / f"{cache_key}.json"
        cache_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception as exc:
        logger.warning("Failed to write cache file %s: %s", cache_key, exc)


def get_client(api_key: str | None = None) -> genai.Client:
    """Create and return a Google GenAI Client."""
    key = api_key or os.getenv("GEMINI_API_KEY") or settings.gemini_api_key
    if not key:
        raise ValueError("GEMINI_API_KEY is not configured.")
    return genai.Client(api_key=key)


def ask_json(
    kind: str,
    prompt: str,
    image_bytes: bytes | None = None,
) -> dict[str, Any] | list[Any] | None:
    """Query Gemma for structured JSON, handling mock mode, caching, and error resilience."""
    # 1. Mock mode
    if _is_mock_mode():
        mock_file = settings.mock_data_dir / f"{kind}.json"
        if mock_file.exists():
            try:
                return json.loads(mock_file.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.warning("Failed to parse mock data file %s: %s", mock_file, exc)
                return None
        logger.warning("Mock data file not found for kind '%s': %s", kind, mock_file)
        return None

    model = os.getenv("GEMMA_MODEL") or settings.gemma_model
    cache_key = _compute_cache_key(model, prompt, image_bytes)

    # 2. Disk cache check
    if not _is_no_cache():
        cached = _read_cache(cache_key)
        if cached is not None:
            return cached

    # 3. Prepare client and contents
    try:
        client = get_client()
    except Exception as exc:
        logger.error("Failed to initialize Gemma client: %s", exc)
        return None

    contents: list[Any] = []
    if image_bytes is not None:
        contents.append(types.Part.from_bytes(data=image_bytes, mime_type="image/png"))
    contents.append(prompt)

    # 4. Generate content
    try:
        response = client.models.generate_content(
            model=model,
            contents=contents,
        )
        text = response.text or ""
    except Exception as exc:
        logger.error("Gemma generate_content API error: %s", exc)
        return None

    parsed = parse_json_loose(text)
    if parsed is not None:
        if not _is_no_cache():
            _write_cache(cache_key, parsed)
        return parsed

    # 5. Retry once if parsing fails
    logger.info("JSON parsing failed, retrying once with valid JSON instruction...")
    try:
        retry_contents = list(contents) + ["Return valid JSON only."]
        retry_response = client.models.generate_content(
            model=model,
            contents=retry_contents,
        )
        retry_text = retry_response.text or ""
        retry_parsed = parse_json_loose(retry_text)
        if retry_parsed is not None:
            if not _is_no_cache():
                _write_cache(cache_key, retry_parsed)
            return retry_parsed
        logger.warning("Retry response could not be parsed as valid JSON.")
        return None
    except Exception as exc:
        logger.error("Gemma retry generate_content API error: %s", exc)
        return None
