"""
Google Gemini API adapter.  §6

Uses urllib.request (stdlib) — zero external dependencies.
API reference: https://ai.google.dev/api/generate-content
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .base import (
    CPEAuthError, CPEError, CPERateLimitError, CPEResponse, ToolUseCall, _trunc,
)

_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
_DEFAULT_MODEL = "gemini-2.0-flash"
_MAX_TOKENS = 8192


class GoogleAdapter:
    """CPEAdapter for Gemini via the Google AI generateContent API."""

    def __init__(self, api_key: str = "", model: str = _DEFAULT_MODEL) -> None:
        self._api_key = api_key or os.environ.get("GOOGLE_API_KEY", "")
        self._model = model

    def invoke(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> CPEResponse:
        # Convert OpenAI-style messages to Gemini contents format
        contents: list[dict[str, Any]] = []
        for msg in messages:
            role = "model" if msg["role"] == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": msg["content"]}]})

        payload: dict[str, Any] = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": contents,
            "generationConfig": {"maxOutputTokens": _MAX_TOKENS},
        }
        if tools:
            payload["tools"] = [{"function_declarations": tools}]
        return _parse_response(_post(self._api_key, self._model, payload))


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def _post(api_key: str, model: str, payload: dict[str, Any]) -> dict[str, Any]:
    if not api_key:
        raise CPEAuthError("GOOGLE_API_KEY not set")
    params = urllib.parse.urlencode({"key": api_key})
    url = f"{_BASE_URL}/{model}:generateContent?{params}"
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        body_text = _trunc(exc.read().decode())
        if exc.code == 401:
            raise CPEAuthError("Google: invalid API key") from exc
        if exc.code == 429:
            raise CPERateLimitError("Google: rate limit exceeded") from exc
        raise CPEError(f"Google: HTTP {exc.code} — {body_text}") from exc
    except urllib.error.URLError as exc:
        raise CPEError(f"Google: network error — {exc.reason}") from exc


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

def _parse_response(data: dict[str, Any]) -> CPEResponse:
    candidate = data.get("candidates", [{}])[0]
    content = candidate.get("content", {})
    text = ""
    tool_calls: list[ToolUseCall] = []
    for part in content.get("parts", []):
        if "text" in part:
            text = part["text"]
        elif "functionCall" in part:
            fc = part["functionCall"]
            tool_calls.append(ToolUseCall(
                id="",
                tool=fc.get("name", ""),
                input=fc.get("args", {}),
            ))
    usage = data.get("usageMetadata", {})
    return CPEResponse(
        text=text,
        tool_use_calls=tool_calls,
        input_tokens=int(usage.get("promptTokenCount", 0)),
        output_tokens=int(usage.get("candidatesTokenCount", 0)),
        stop_reason=candidate.get("finishReason", ""),
    )
