"""
OpenAI / OpenAI-compatible API adapter.  §6

Uses urllib.request (stdlib) — zero external dependencies.
Compatible with any OpenAI-compatible endpoint (set OPENAI_BASE_URL to override).
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from .base import CPEAuthError, CPEError, CPERateLimitError, CPEResponse, FCPContext, ToolUseCall, _trunc

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

    def invoke(self, context: FCPContext) -> CPEResponse:
        messages = _build_messages(context)
        payload: dict[str, Any] = {
            "model": self._model,
            "max_tokens": _MAX_TOKENS,
            "messages": messages,
        }
        if context.tools:
            payload["tools"] = context.tools
        return _parse_response(_post(self._api_key, self._base_url, payload))


# ---------------------------------------------------------------------------
# Message formatting
# ---------------------------------------------------------------------------

def _build_messages(ctx: FCPContext) -> list[dict[str, Any]]:
    system_parts: list[str] = []
    for p in ctx.persona:
        system_parts.append(p)
    system_parts.append(ctx.boot_protocol)
    system_parts.append(f"[SKILLS INDEX]\n{ctx.skills_index}")
    for block in ctx.skill_blocks:
        system_parts.append(block)

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": "\n\n".join(system_parts)},
    ]

    user_parts: list[str] = []
    if ctx.memory:
        user_parts.append("[MEMORY]\n" + "\n\n".join(ctx.memory))
    if ctx.session:
        lines = [json.dumps(e, separators=(",", ":")) for e in ctx.session]
        user_parts.append("[SESSION]\n" + "\n".join(lines))
    if ctx.presession:
        lines = [json.dumps(e, separators=(",", ":")) for e in ctx.presession]
        user_parts.append("[PRESESSION]\n" + "\n".join(lines))

    messages.append({"role": "user", "content": "\n\n".join(user_parts) if user_parts else "(no context)"})
    return messages


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def _post(api_key: str, base_url: str, payload: dict[str, Any]) -> dict[str, Any]:
    if not api_key:
        raise CPEAuthError("OPENAI_API_KEY not set")
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        body_text = _trunc(exc.read().decode())
        if exc.code == 401:
            raise CPEAuthError("OpenAI: invalid API key") from exc
        if exc.code == 429:
            raise CPERateLimitError("OpenAI: rate limit exceeded") from exc
        raise CPEError(f"OpenAI: HTTP {exc.code} — {body_text}") from exc
    except urllib.error.URLError as exc:
        raise CPEError(f"OpenAI: network error — {exc.reason}") from exc


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

def _parse_response(data: dict[str, Any]) -> CPEResponse:
    choice = data.get("choices", [{}])[0]
    message = choice.get("message", {})
    text = message.get("content") or ""
    tool_calls: list[ToolUseCall] = []
    for tc in message.get("tool_calls", []):
        raw_args = tc.get("function", {}).get("arguments", "{}")
        try:
            parsed_input = json.loads(raw_args)
        except (json.JSONDecodeError, TypeError):
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
