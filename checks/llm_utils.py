"""
Shared Gemini call helper.

Root cause of most bugs found during review: check files were still calling
`client.messages.create(...)` — the Anthropic SDK shape — against a
`google.genai.Client`, which has no `.messages` attribute. Every sub-check
using that pattern silently failed and returned {"points": 0, "error": ...}.

This module is the one place that knows how to correctly call Gemini,
with:
  - retry + exponential backoff on 429 RESOURCE_EXHAUSTED (free tier is
    rate-limited hard; the old code had zero retry logic)
  - a consistent `available: bool` on every response, so callers can tell
    "genuinely low score" apart from "call failed" — that distinction was
    missing everywhere and is the direct cause of blank current_associations
    and the fake 36/Critical verdict.
  - JSON-mode helper that strips code fences and reports parse failures
    as `available=False` instead of raising.
"""

import json
import re
import time

from google import genai
from google.genai import types

MODEL = "gemini-2.5-flash"
MAX_RETRIES = 4
BASE_DELAY = 2.0  # seconds


def _is_rate_limit(exc: Exception) -> bool:
    return "429" in str(exc) or "RESOURCE_EXHAUSTED" in str(exc)


def _call_with_retry(fn, *args, **kwargs):
    """Call `fn`, retrying with exponential backoff on rate limits."""
    last_err = None
    for attempt in range(MAX_RETRIES):
        try:
            return fn(*args, **kwargs), None
        except Exception as e:
            last_err = e
            if _is_rate_limit(e) and attempt < MAX_RETRIES - 1:
                #delay = BASE_DELAY * (2 ** attempt)
                delay=10
                time.sleep(delay)
                continue
            break
    return None, last_err


def generate(client: genai.Client, prompt: str, use_search: bool = False,
             max_tokens: int = 600) -> dict:
    """
    Call Gemini once (with retry/backoff). Returns:
      {"available": bool, "text": str, "error": str|None}
    """
    config_kwargs = {"max_output_tokens": max_tokens}
    if use_search:
        config_kwargs["tools"] = [types.Tool(google_search=types.GoogleSearch())]
    config = types.GenerateContentConfig(**config_kwargs)

    def _do():
        return client.models.generate_content(model=MODEL, contents=prompt, config=config)

    response, err = _call_with_retry(_do)

    if err is not None:
        reason = "Rate limit exceeded (Gemini free tier)" if _is_rate_limit(err) else str(err)
        return {"available": False, "text": "", "error": reason}

    text = getattr(response, "text", None)
    if not text:
        # Fallback: assemble from candidate parts if .text shortcut is empty
        try:
            parts = response.candidates[0].content.parts
            text = " ".join(p.text for p in parts if hasattr(p, "text"))
        except Exception:
            text = ""

    if not text:
        return {"available": False, "text": "", "error": "Empty response from model"}

    return {"available": True, "text": text, "error": None}


def generate_json(client: genai.Client, prompt: str, schema=None, use_search: bool = False,
                   max_tokens: int = 600) -> dict:
    """
    Call Gemini and parse the reply as JSON. Returns:
      {"available": bool, "data": dict, "error": str|None}
    """
    result = generate(client, prompt, use_search=use_search, max_tokens=max_tokens)
    if not result["available"]:
        return {"available": False, "data": {}, "error": result["error"]}

    cleaned = re.sub(r"```json|```", "", result["text"]).strip()
    try:
        raw = json.loads(cleaned)

        if schema:
            validated = schema.model_validate(raw)
            return {
                "available": True,
                "data": validated,
                "error": None,
            }
        
        return {"available": True, "data": raw, "error": None}
    except Exception as e:
        return {"available": False, "data": {}, "error": f"Could not parse model JSON: {e}"}