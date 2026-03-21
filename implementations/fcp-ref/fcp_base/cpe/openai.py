"""
OpenAI / OpenAI-compatible API adapter.  §6

Uses urllib.request (stdlib) — zero external dependencies.
Compatible with any OpenAI-compatible endpoint (set OPENAI_BASE_URL to override).
"""

from __future__ import annotations

import json
import os
from typing import Any

from .base import CPEAuthError, CPEResponse, ToolUseCall, _trunc
from ._http import post_json

_DEFAULT_BASE_URL = "https://api.openai.com/v1"
_DEFAULT_MODEL = "gpt-4o"
_MAX_TOKENS = 8192


class OpenAIAdapter:
    """CPEAdapter for OpenAI and OpenAI-compatible endpoints."""

    def __init__(self, api_key: str = "", model: str = _DEFAULT_MODEL, base_url: str = "") -> None:
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self._model = model
        base = base_url or os.environ.get("OPENAI_BASE_URL", _DEFAULT_BASE_URL)
        self._base_url = base.rstrip("/")

    def invoke(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> CPEResponse:
        full_messages = [{"role": "system", "content": system}] + messages
        payload: dict[str, Any] = {
            "model": self._model,
            "max_tokens": _MAX_TOKENS,
            "messages": full_messages,
        }
        if tools:
            payload["tools"] = tools
        return _parse_response(_post(self._api_key, self._base_url, payload))


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def _post(api_key: str, base_url: str, payload: dict[str, Any]) -> dict[str, Any]:
    if not api_key:
        raise CPEAuthError("OPENAI_API_KEY not set")
    return post_json(
        url=f"{base_url}/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        payload=payload,
        provider="OpenAI",
    )


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

def _parse_response(data: dict[str, Any]) -> CPEResponse:
    choice = data.get("choices", [{}])[0]
    message = choice.get("message", {})
    text = message.get("content") or ""
    tool_calls: list[ToolUseCall] = []
    for tc in message.get("tool_calls") or []:
        raw_args = tc.get("function", {}).get("arguments", "{}")
        try:
            parsed_input = json.loads(raw_args)
        except (json.JSONDecodeError, TypeError) as exc:
            # Log parse failure for debugging (silent fallback to {})
            import sys
            tool_name = tc.get("function", {}).get("name", "unknown")
            print(
                f"[OpenAI] Warning: failed to parse tool arguments for '{tool_name}': {exc}",
                file=sys.stderr,
            )
            parsed_input = {}
        tool_calls.append(ToolUseCall(
            id=tc.get("id", ""),
            tool=tc.get("function", {}).get("name", ""),
            input=parsed_input,
        ))
    usage = data.get("usage", {})
    return CPEResponse(
        text=text,
        tool_use_calls=tool_calls,
        input_tokens=int(usage.get("prompt_tokens", 0)),
        output_tokens=int(usage.get("completion_tokens", 0)),
        stop_reason=choice.get("finish_reason", ""),
    )
