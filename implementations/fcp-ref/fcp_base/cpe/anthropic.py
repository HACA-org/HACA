"""
Anthropic Messages API adapter.  §6

Uses urllib.request (stdlib) — zero external dependencies.
API reference: https://docs.anthropic.com/en/api/messages

Supports extended thinking, tool use, and latest Claude models.
API version: 2024-06-15 (supports thinking blocks, improved tool use).
"""

from __future__ import annotations

import os
from typing import Any

from .base import CPEAuthError, CPEResponse, ToolUseCall, _trunc
from ._http import post_json

_API_URL = "https://api.anthropic.com/v1/messages"
_API_VERSION = "2024-06-15"  # Updated: 2023-06-01 → 2024-06-15
_DEFAULT_MODEL = "claude-opus-4-6"
_MAX_TOKENS = 8192


class AnthropicAdapter:
    """CPEAdapter for Claude via the Anthropic Messages API."""

    def __init__(self, api_key: str = "", model: str = _DEFAULT_MODEL) -> None:
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._model = model

    def invoke(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> CPEResponse:
        payload: dict[str, Any] = {
            "model": self._model,
            "max_tokens": _MAX_TOKENS,
            "system": system,
            "messages": messages,
        }
        if tools:
            payload["tools"] = tools
        return _parse_response(_post(self._api_key, payload))


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def _post(api_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    if not api_key:
        raise CPEAuthError("ANTHROPIC_API_KEY not set")
    return post_json(
        url=_API_URL,
        headers={
            "x-api-key": api_key,
            "anthropic-version": _API_VERSION,
            "content-type": "application/json",
        },
        payload=payload,
        provider="Anthropic",
    )


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
