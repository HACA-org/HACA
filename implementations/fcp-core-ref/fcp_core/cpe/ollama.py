"""
Ollama local inference adapter.  §6

Uses urllib.request (stdlib) — zero external dependencies.
Topology is always TRANSPARENT — Ollama runs locally and is fully isolated.
Base URL defaults to http://localhost:11434 (set OLLAMA_BASE_URL to override).

Auto-detection: is_available() checks if Ollama is reachable before invoking.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from .base import CPEError, CPEResponse, FCPContext, ToolUseCall, _trunc

_DEFAULT_BASE_URL = "http://localhost:11434"
_DEFAULT_MODEL = "llama3.2"
_MAX_TOKENS = 8192


class OllamaAdapter:
    """CPEAdapter for Ollama local inference (OpenAI-compatible /api/chat)."""

    def __init__(self, api_key: str = "", model: str = _DEFAULT_MODEL, base_url: str = "") -> None:
        self._model = model
        base = base_url or os.environ.get("OLLAMA_BASE_URL", _DEFAULT_BASE_URL)
        self._base_url = base.rstrip("/")

    def invoke(self, context: FCPContext) -> CPEResponse:
        messages = _build_messages(context)
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "stream": False,
            "options": {"num_predict": _MAX_TOKENS},
        }
        if context.tools:
            payload["tools"] = context.tools
        return _parse_response(_post(self._base_url, payload))

    def is_available(self) -> bool:
        """Return True if the Ollama server is reachable."""
        try:
            with urllib.request.urlopen(f"{self._base_url}/api/tags", timeout=2):
                return True
        except (urllib.error.URLError, OSError):
            return False


# ---------------------------------------------------------------------------
# Message formatting  (Ollama follows OpenAI Chat format)
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

def _post(base_url: str, payload: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{base_url}/api/chat",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        body_text = _trunc(exc.read().decode())
        raise CPEError(f"Ollama: HTTP {exc.code} — {body_text}") from exc
    except urllib.error.URLError as exc:
        raise CPEError(f"Ollama: network error — {exc.reason}") from exc


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

def _parse_response(data: dict[str, Any]) -> CPEResponse:
    message = data.get("message", {})
    text = message.get("content") or ""
    tool_calls: list[ToolUseCall] = []
    for tc in message.get("tool_calls", []):
        fn = tc.get("function", {})
        raw_args = fn.get("arguments", {})
        parsed_input = raw_args if isinstance(raw_args, dict) else {}
        tool_calls.append(ToolUseCall(
            id="",
            tool=fn.get("name", ""),
            input=parsed_input,
        ))
    return CPEResponse(
        text=text,
        tool_use_calls=tool_calls,
        input_tokens=int(data.get("prompt_eval_count", 0)),
        output_tokens=int(data.get("eval_count", 0)),
        stop_reason=data.get("done_reason", ""),
    )
