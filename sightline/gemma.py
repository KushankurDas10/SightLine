"""Gemma model interface via the Gemini API (google-genai)."""

import hashlib
import json
import logging
import os
import re
import time
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


def _get_thinking_config() -> types.ThinkingConfig | None:
    """Resolve ThinkingConfig based on GEMMA_THINKING env var (default: 'minimal')."""
    val = (os.getenv("GEMMA_THINKING") or settings.gemma_thinking).strip().lower()
    if val == "default":
        return None
    return types.ThinkingConfig(thinking_level=types.ThinkingLevel.MINIMAL)


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
    image_mime: str = "image/png",
    timeout_seconds: float = 45.0,
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
        contents.append(types.Part.from_bytes(data=image_bytes, mime_type=image_mime))
    contents.append(prompt)

    thinking_cfg = _get_thinking_config()
    max_tokens = 1500 if thinking_cfg is not None else 3500

    timeout_ms = int(timeout_seconds * 1000)
    http_options = types.HttpOptions(
        timeout=timeout_ms,
        retry_options=types.HttpRetryOptions(attempts=1),
    )
    config = types.GenerateContentConfig(
        max_output_tokens=max_tokens,
        http_options=http_options,
        thinking_config=thinking_cfg,
    )

    prompt_len = len(prompt)
    image_len = len(image_bytes) if image_bytes else 0
    print(f"\n[Gemma Call Diagnostics]: kind={kind}, model={model}")
    print(f"  Prompt size: {prompt_len} chars")
    print(f"  Image size:  {image_len} bytes")
    logger.info(
        "Gemma request: kind=%s, model=%s, prompt_len=%d, image_len=%d",
        kind,
        model,
        prompt_len,
        image_len,
    )

    # 4. Generate content (Attempt 1)
    attempt_count = 1
    t0 = time.perf_counter()
    try:
        response = client.models.generate_content(
            model=model,
            contents=contents,
            config=config,
        )
        t_attempt1 = time.perf_counter() - t0
        text = response.text or ""
        print(f"  Attempt 1 took: {t_attempt1:.2f}s | Output length: {len(text)} chars")
        logger.info("Gemma Attempt 1 took %.2fs, output len=%d", t_attempt1, len(text))
    except Exception as exc:
        t_attempt1 = time.perf_counter() - t0
        if thinking_cfg is not None:
            logger.warning(
                "Gemma rejected thinking_config (%s). Retrying without thinking_config...",
                exc,
            )
            print(f"  Gemma model/SDK rejected thinking_config: {exc}. Retrying once without it...")
            config = types.GenerateContentConfig(
                max_output_tokens=3500,
                http_options=http_options,
                thinking_config=None,
            )
            try:
                t0_fb = time.perf_counter()
                response = client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=config,
                )
                t_attempt1 = time.perf_counter() - t0_fb
                text = response.text or ""
                print(f"  Fallback took: {t_attempt1:.2f}s | Output length: {len(text)} chars")
                logger.info(
                    "Gemma fallback took %.2fs, output len=%d", t_attempt1, len(text)
                )
            except Exception as fb_exc:
                print(f"  Fallback attempt error: {fb_exc}")
                logger.error("Gemma generate_content API error on fallback: %s", fb_exc)
                return None
        else:
            print(f"  Attempt 1 error after {t_attempt1:.2f}s: {exc}")
            logger.error("Gemma generate_content API error (Attempt 1): %s", exc)
            return None

    parsed = parse_json_loose(text)
    if parsed is not None:
        print(f"  JSON parsing: SUCCESS on attempt {attempt_count}")
        if not _is_no_cache():
            _write_cache(cache_key, parsed)
        return parsed

    # 5. Retry once ONLY if JSON parsing fails (Attempt 2)
    attempt_count = 2
    print("  JSON parsing: FAILED on attempt 1. Retrying once with 'Return valid JSON only.'...")
    logger.info("JSON parsing failed on attempt 1, retrying once...")
    t0_retry = time.perf_counter()
    try:
        retry_contents = list(contents) + ["Return valid JSON only."]
        retry_response = client.models.generate_content(
            model=model,
            contents=retry_contents,
            config=config,
        )
        t_attempt2 = time.perf_counter() - t0_retry
        retry_text = retry_response.text or ""
        print(f"  Attempt 2 took: {t_attempt2:.2f}s | Output length: {len(retry_text)} chars")
        logger.info("Gemma Attempt 2 took %.2fs, output len=%d", t_attempt2, len(retry_text))

        retry_parsed = parse_json_loose(retry_text)
        if retry_parsed is not None:
            print("  JSON parsing: SUCCESS on attempt 2")
            if not _is_no_cache():
                _write_cache(cache_key, retry_parsed)
            return retry_parsed
        print("  JSON parsing: FAILED on attempt 2")
        logger.warning("Retry response could not be parsed as valid JSON.")
        return None
    except Exception as exc:
        t_attempt2 = time.perf_counter() - t0_retry
        print(f"  Attempt 2 error after {t_attempt2:.2f}s: {exc}")
        logger.error("Gemma retry generate_content API error: %s", exc)
        return None
