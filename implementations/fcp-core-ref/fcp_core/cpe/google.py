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
    CPEAuthError, CPEError, CPERateLimitError, CPEResponse, FCPContext, ToolUseCall, _trunc,
    build_system, build_instruction_block, build_history,
)

_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
_DEFAULT_MODEL = "gemini-2.0-flash"
_MAX_TOKENS = 8192


class GoogleAdapter:
    """CPEAdapter for Gemini via the Google AI generateContent API."""

    def __init__(self, api_key: str = "", model: str = _DEFAULT_MODEL) -> None:
        self._api_key = api_key or os.environ.get("GOOGLE_API_KEY", "")
        self._model = model

    def invoke(self, context: FCPContext) -> CPEResponse:
        system_instruction, contents = _build_contents(context)
        payload: dict[str, Any] = {
            "system_instruction": {"parts": [{"text": system_instruction}]},
            "contents": contents,
            "generationConfig": {"maxOutputTokens": _MAX_TOKENS},
        }
        if context.tools:
            payload["tools"] = [{"function_declarations": context.tools}]
        return _parse_response(_post(self._api_key, self._model, payload))


# ---------------------------------------------------------------------------
# Message formatting
# ---------------------------------------------------------------------------

def _build_contents(ctx: FCPContext) -> tuple[str, list[dict[str, Any]]]:
    system_instruction = build_system(ctx)

    contents: list[dict[str, Any]] = [
        {"role": "user", "parts": [{"text": build_instruction_block(ctx)}]},
        {"role": "model", "parts": [{"text": "Understood. I am ready."}]},
    ]

    history = build_history(ctx)
    for role, text in history:
        g_role = "model" if role == "assistant" else "user"
        contents.append({"role": g_role, "parts": [{"text": text}]})

    if not history:
        contents.append({"role": "user", "parts": [{"text": "(awaiting first message)"}]})

    return system_instruction, contents


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
