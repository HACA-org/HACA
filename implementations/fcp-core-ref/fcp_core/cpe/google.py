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
        # Track function calls from the last model turn so we can build functionResponse
        self._last_function_calls: list[dict[str, Any]] = []

    def invoke(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> CPEResponse:
        contents = _build_contents(messages, self._last_function_calls)

        payload: dict[str, Any] = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": contents,
            "generationConfig": {"maxOutputTokens": _MAX_TOKENS},
        }
        if tools:
            payload["tools"] = [{"function_declarations": [_convert_tool(t) for t in tools]}]
        response = _parse_response(_post(self._api_key, self._model, payload))
        # Save function calls emitted this turn for the next invoke
        self._last_function_calls = [
            {"name": c.tool, "args": c.input} for c in response.tool_use_calls
        ]
        return response


def _build_contents(
    messages: list[dict[str, Any]],
    last_function_calls: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert chat_history to Gemini contents format.

    The chat_history alternates user/assistant. When an assistant turn had
    tool_use (content=="") the following user turn contains the tool results
    as JSON. We detect this pattern and emit functionResponse parts instead
    of text, using last_function_calls to map results to function names.
    """
    contents: list[dict[str, Any]] = []
    i = 0
    while i < len(messages):
        msg = messages[i]
        role = msg["role"]
        content = msg.get("content", "")

        if role == "assistant":
            if not content:
                # Tool-use turn — will be reconstructed from last_function_calls
                # on the *previous* iteration. Here we emit an empty model turn
                # as placeholder so the functionResponse follows correctly.
                # Actually we need to emit the functionCall parts.
                # Look ahead: next user msg is the tool result.
                # We emit model turn with functionCall parts from last_function_calls
                # only when this is the last assistant turn before a user result turn.
                # Simpler approach: emit a minimal model turn with text placeholder
                # and let the functionResponse user turn follow.
                contents.append({"role": "model", "parts": [{"text": ""}]})
            else:
                contents.append({"role": "model", "parts": [{"text": content}]})
            i += 1
            continue

        # user turn — check if it's a tool result (JSON with "results" key)
        if role == "user" and last_function_calls and i > 0 and messages[i - 1]["role"] == "assistant" and not messages[i - 1].get("content", ""):
            # Try to parse as tool result
            parsed = _try_parse_tool_result(content)
            if parsed is not None:
                # Build functionResponse parts, one per function call
                parts: list[dict[str, Any]] = []
                results = parsed.get("results", [parsed])
                for j, fc in enumerate(last_function_calls):
                    resp = results[j] if j < len(results) else {}
                    parts.append({
                        "functionResponse": {
                            "name": fc["name"],
                            "response": {"output": resp},
                        }
                    })
                if parts:
                    contents.append({"role": "user", "parts": parts})
                    i += 1
                    continue

        contents.append({"role": "user", "parts": [{"text": content}]})
        i += 1

    return contents


def _try_parse_tool_result(text: str) -> dict[str, Any] | None:
    """Return parsed dict if text is a tool result JSON, else None."""
    if not text:
        return None
    try:
        data = json.loads(text)
        if isinstance(data, dict) and "results" in data:
            return data
    except (json.JSONDecodeError, ValueError):
        pass
    return None


def _convert_tool(tool: dict[str, Any]) -> dict[str, Any]:
    """Convert OpenAI-style tool declaration to Gemini function_declaration format."""
    result: dict[str, Any] = {"name": tool["name"]}
    if "description" in tool:
        result["description"] = tool["description"]
    schema = tool.get("input_schema", {})
    if schema:
        result["parameters"] = schema
    return result


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
