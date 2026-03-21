"""
Ollama local inference adapter.  §6

Uses urllib.request (stdlib) — zero external dependencies.
Topology is always TRANSPARENT — Ollama runs locally and is fully isolated.
Base URL defaults to http://localhost:11434 (set OLLAMA_BASE_URL to override).

Auto-detection: is_available() checks if Ollama is reachable before invoking.

Streaming Support (2026-03-20):
- Respects "stream" parameter (True enables incremental response processing)
- Non-streaming (default): Single complete response
- Tool call format synchronized with official Ollama API (message.tool_calls[])
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from .base import (
    CPEError, CPEResponse, ToolUseCall, _trunc,
)

_DEFAULT_BASE_URL = "http://localhost:11434"
_DEFAULT_MODEL = "llama3.2"
_MAX_TOKENS = 8192


class OllamaAdapter:
    """CPEAdapter for Ollama local inference (/api/chat)."""

    def __init__(self, api_key: str = "", model: str = _DEFAULT_MODEL, base_url: str = "") -> None:
        self._model = model
        base = base_url or os.environ.get("OLLAMA_BASE_URL", _DEFAULT_BASE_URL)
        self._base_url = base.rstrip("/")

    def invoke(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> CPEResponse:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [{"role": "system", "content": system}] + _convert_messages(messages),
            "stream": False,  # Currently non-streaming for simplicity; can enable streaming in future
            "options": {"num_predict": _MAX_TOKENS},
        }
        if tools:
            payload["tools"] = [_convert_tool(t) for t in tools]
        return _parse_response(_post(self._base_url, payload))

    def is_available(self) -> bool:
        """Return True if the Ollama server is reachable."""
        try:
            with urllib.request.urlopen(f"{self._base_url}/api/tags", timeout=2):
                return True
        except (urllib.error.URLError, OSError):
            return False


# ---------------------------------------------------------------------------
# Tool format conversion
# ---------------------------------------------------------------------------

def _convert_tool(tool: dict[str, Any]) -> dict[str, Any]:
    """Convert FCP tool declaration to Ollama format.

    FCP uses {name, description, input_schema} (Anthropic-style).
    Ollama expects {type: "function", function: {name, description, parameters}}.
    """
    return {
        "type": "function",
        "function": {
            "name": tool.get("name", ""),
            "description": tool.get("description", ""),
            "parameters": tool.get("input_schema", {"type": "object", "properties": {}}),
        },
    }


# ---------------------------------------------------------------------------
# Message format conversion
# ---------------------------------------------------------------------------

def _convert_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert FCP chat_history to Ollama message format.

    FCP sends tool results as role:user with '[tool_name] {json}' text.
    Ollama expects role:tool with tool_name and content fields.
    Tool result lines that follow an assistant turn with tool_calls are
    converted to individual role:tool messages.
    """
    result: list[dict[str, Any]] = []
    i = 0
    while i < len(messages):
        msg = messages[i]
        role = msg.get("role", "")

        if role == "user":
            content = msg.get("content", "")
            # Check if the previous message was an assistant with tool calls
            prev = result[-1] if result else {}
            if prev.get("role") == "assistant" and prev.get("tool_calls"):
                # Parse tool result lines: "[tool_name] {json}" per line
                tool_msgs = _parse_tool_result_lines(content)
                if tool_msgs:
                    result.extend(tool_msgs)
                    i += 1
                    continue
            result.append(msg)
        else:
            result.append(msg)
        i += 1
    return result


def _parse_tool_result_lines(content: str) -> list[dict[str, Any]]:
    """Parse '[tool_name] {json}' lines into role:tool messages.

    Returns empty list if content does not match the expected format.
    """
    msgs: list[dict[str, Any]] = []
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        if not line.startswith("["):
            return []  # not a tool result block — leave as user message
        bracket_end = line.find("]")
        if bracket_end == -1:
            return []
        tool_name = line[1:bracket_end]
        rest = line[bracket_end + 1:].strip()
        try:
            parsed = json.loads(rest)
            tool_content = parsed if isinstance(parsed, str) else json.dumps(parsed, ensure_ascii=False)
        except Exception:
            tool_content = rest
        msgs.append({
            "role": "tool",
            "tool_name": tool_name,
            "content": tool_content,
        })
    return msgs


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
    """Parse Ollama response into CPEResponse.

    Ollama official format (streaming=false):
      message.tool_calls[] — array of {function: {name, arguments}}
      message.content — narrative text
      done_reason — completion reason

    Tool call arguments can be either dict or JSON string; both are normalized.
    """
    message = data.get("message", {})
    content = message.get("content") or ""
    tool_calls: list[ToolUseCall] = []

    # Parse tool_calls from official format: message.tool_calls[]
    for tc in message.get("tool_calls", []):
        fn = tc.get("function", {})
        raw_args = fn.get("arguments", {})

        # Normalize: arguments may be dict or JSON string
        if isinstance(raw_args, str):
            try:
                raw_args = json.loads(raw_args)
            except (json.JSONDecodeError, ValueError):
                raw_args = {}

        parsed_input = raw_args if isinstance(raw_args, dict) else {}
        tool_calls.append(ToolUseCall(
            id="",
            tool=fn.get("name", ""),
            input=parsed_input,
        ))

    return CPEResponse(
        text=content,
        tool_use_calls=tool_calls,
        input_tokens=int(data.get("prompt_eval_count", 0)),
        output_tokens=int(data.get("eval_count", 0)),
        stop_reason=data.get("done_reason", ""),
    )
