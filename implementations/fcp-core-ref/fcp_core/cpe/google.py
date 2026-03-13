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

from .base import CPEAuthError, CPEError, CPERateLimitError, CPEResponse, FCPContext, ToolUseCall, _trunc

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
    system_parts: list[str] = []
    for p in ctx.persona:
        system_parts.append(p)
    system_parts.append(ctx.boot_protocol)
    system_parts.append(f"[SKILLS INDEX]\n{ctx.skills_index}")
    for block in ctx.skill_blocks:
        system_parts.append(block)
    system_instruction = "\n\n".join(system_parts)

    user_parts: list[str] = []
    if ctx.memory:
        user_parts.append("[MEMORY]\n" + "\n\n".join(ctx.memory))
    if ctx.session:
        lines = [json.dumps(e, separators=(",", ":")) for e in ctx.session]
        user_parts.append("[SESSION]\n" + "\n".join(lines))
    if ctx.presession:
        lines = [json.dumps(e, separators=(",", ":")) for e in ctx.presession]
        user_parts.append("[PRESESSION]\n" + "\n".join(lines))

    user_text = "\n\n".join(user_parts) if user_parts else "(no context)"
    contents: list[dict[str, Any]] = [{"role": "user", "parts": [{"text": user_text}]}]
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
