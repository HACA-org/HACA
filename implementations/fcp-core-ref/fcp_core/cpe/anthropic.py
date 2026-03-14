"""
Anthropic Messages API adapter.  §6

Uses urllib.request (stdlib) — zero external dependencies.
API reference: https://docs.anthropic.com/en/api/messages
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from .base import (
    CPEAuthError, CPEError, CPERateLimitError, CPEResponse, FCPContext, ToolUseCall, _trunc,
    build_system, build_instruction_block, build_history,
)

_API_URL = "https://api.anthropic.com/v1/messages"
_API_VERSION = "2023-06-01"
_DEFAULT_MODEL = "claude-opus-4-6"
_MAX_TOKENS = 8192


class AnthropicAdapter:
    """CPEAdapter for Claude via the Anthropic Messages API."""

    def __init__(self, api_key: str = "", model: str = _DEFAULT_MODEL) -> None:
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._model = model

    def invoke(self, context: FCPContext) -> CPEResponse:
        system, messages = _build_messages(context)
        payload: dict[str, Any] = {
            "model": self._model,
            "max_tokens": _MAX_TOKENS,
            "system": system,
            "messages": messages,
        }
        if context.tools:
            payload["tools"] = context.tools
        return _parse_response(_post(self._api_key, payload))


# ---------------------------------------------------------------------------
# Message formatting
# ---------------------------------------------------------------------------

def _build_messages(ctx: FCPContext) -> tuple[str, list[dict[str, Any]]]:
    system = build_system(ctx)

    messages: list[dict[str, Any]] = [
        {"role": "user", "content": build_instruction_block(ctx)},
        {"role": "assistant", "content": "Understood. I am ready."},
    ]

    for role, text in build_history(ctx):
        messages.append({"role": role, "content": text})

    if not build_history(ctx):
        messages.append({"role": "user", "content": "(awaiting first message)"})

    return system, messages


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def _post(api_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    if not api_key:
        raise CPEAuthError("ANTHROPIC_API_KEY not set")
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        _API_URL,
        data=body,
        headers={
            "x-api-key": api_key,
            "anthropic-version": _API_VERSION,
            "content-type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        body_text = _trunc(exc.read().decode())
        if exc.code == 401:
            raise CPEAuthError("Anthropic: invalid API key") from exc
        if exc.code == 429:
            raise CPERateLimitError("Anthropic: rate limit exceeded") from exc
        raise CPEError(f"Anthropic: HTTP {exc.code} — {body_text}") from exc
    except urllib.error.URLError as exc:
        raise CPEError(f"Anthropic: network error — {exc.reason}") from exc


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

def _parse_response(data: dict[str, Any]) -> CPEResponse:
    text = ""
    tool_calls: list[ToolUseCall] = []
    for block in data.get("content", []):
        btype = block.get("type", "")
        if btype == "text":
            text = block.get("text", "")
        elif btype == "tool_use":
            tool_calls.append(ToolUseCall(
                id=block.get("id", ""),
                tool=block.get("name", ""),
                input=block.get("input", {}),
            ))
    usage = data.get("usage", {})
    return CPEResponse(
        text=text,
        tool_use_calls=tool_calls,
        input_tokens=int(usage.get("input_tokens", 0)),
        output_tokens=int(usage.get("output_tokens", 0)),
        stop_reason=data.get("stop_reason", ""),
    )
