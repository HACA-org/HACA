"""
Ollama local inference adapter.  §6

Uses urllib.request (stdlib) — zero external dependencies.
Topology is always TRANSPARENT — Ollama runs locally and is fully isolated.
Base URL defaults to http://localhost:11434 (set OLLAMA_BASE_URL to override).

Auto-detection: is_available() checks if Ollama is reachable before invoking.

Streaming Support (2026-03-21):
- Optional streaming mode (default: disabled for backward compatibility)
- When enabled: accumulates streaming chunks, extracts tool calls incrementally
- Non-streaming: Single complete response (current default)
- Tool call format synchronized with official Ollama API (message.tool_calls[])
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

from .base import (
    CPEError, CPEResponse, ToolUseCall, _trunc, validate_invoke_inputs,
)

_DEFAULT_BASE_URL = "http://localhost:11434"
_DEFAULT_MODEL = "llama3.2"
_MAX_TOKENS = 8192


class OllamaAdapter:
    """CPEAdapter for Ollama local inference (/api/chat).

    Supports optional streaming mode for incremental response processing.
    """

    def __init__(self, api_key: str = "", model: str = _DEFAULT_MODEL, base_url: str = "", enable_streaming: bool = False) -> None:
        self._model = model
        base = base_url or os.environ.get("OLLAMA_BASE_URL", _DEFAULT_BASE_URL)
        self._base_url = base.rstrip("/")
        self._enable_streaming = enable_streaming

    def invoke(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> CPEResponse:
        # Validate inputs early
        validate_invoke_inputs(system, messages, tools)

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [{"role": "system", "content": system}] + _convert_messages(messages),
            "stream": self._enable_streaming,
            "options": {"num_predict": _MAX_TOKENS},
        }
        if tools:
            payload["tools"] = [_convert_tool(t) for t in tools]

        if self._enable_streaming:
            return _parse_streaming_response(_post_streaming(self._base_url, payload))
        else:
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
    """Convert FCP chat_history to Ollama multi-turn tool use format.

    Ollama (OpenAI-compatible) requires a strict message structure for tool use:
      assistant: {content: null, tool_calls: [{id, type, function: {name, arguments}}]}
      tool:      {role: "tool", tool_call_id: <matching id>, content: "..."}

    FCP stores tool results as:
      assistant: {content: ""} or {content: text}  (NO tool_calls field)
      user: {content: "[tool_name] {json}\\n[tool_name] {json}"}

    This function detects the tool result pattern and reconstructs the proper format:
    - Updates the preceding assistant message to include tool_calls
    - Emits role:tool messages with matching tool_call_id

    Detection: a user message that follows any assistant turn AND starts with "["
    (handles both empty-content assistant turns AND text+tools turns).
    """
    result: list[dict[str, Any]] = []
    i = 0
    while i < len(messages):
        msg = messages[i]
        role = msg.get("role", "")

        if role == "user":
            content = msg.get("content", "")
            prev_idx = len(result) - 1
            prev = result[prev_idx] if result else {}

            # Detect tool result turn: follows any assistant turn AND content is "[tool] {json}"
            if prev.get("role") == "assistant" and content.startswith("["):
                tool_parsed = _parse_tool_result_lines(content)
                if tool_parsed:
                    # Reconstruct proper Ollama tool_calls on the assistant turn.
                    # We don't have original call args, so use "{}" — the name is what matters
                    # for conversation coherence. IDs are synthetic but must match.
                    synthetic_calls = [
                        {
                            "id": f"call_{j}",
                            "type": "function",
                            "function": {
                                "name": tm["tool_name"],
                                "arguments": {},
                            },
                        }
                        for j, tm in enumerate(tool_parsed)
                    ]
                    # text+tools case: sentinel {assistant: ""} follows {assistant: "text"}.
                    # Ollama requires tool_calls on the SAME turn as the text — merge into
                    # the preceding text turn and discard the empty sentinel.
                    if not prev.get("content", "") and prev_idx > 0 and result[prev_idx - 1].get("role") == "assistant":
                        result.pop(prev_idx)  # discard empty sentinel
                        result[prev_idx - 1] = dict(result[prev_idx - 1], tool_calls=synthetic_calls)
                    else:
                        # plain tool-only case: add tool_calls to the assistant turn (empty or text)
                        result[prev_idx] = dict(prev, tool_calls=synthetic_calls)
                    # Emit role:tool messages with matching tool_call_id
                    for j, tm in enumerate(tool_parsed):
                        result.append({
                            "role": "tool",
                            "tool_call_id": f"call_{j}",
                            "content": tm["content"],
                        })
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
    """Non-streaming POST to Ollama /api/chat."""
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


def _post_streaming(base_url: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Streaming POST to Ollama /api/chat (returns accumulated chunks).

    Accumulates chunks up to 100MB to prevent memory exhaustion.
    """
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{base_url}/api/chat",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    chunks: list[dict[str, Any]] = []
    accumulated_size = 0
    _MAX_STREAMING_SIZE_BYTES = 100 * 1024 * 1024  # 100MB limit
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            for line in resp:
                if line.strip():
                    chunk = json.loads(line.decode())
                    chunks.append(chunk)
                    # Track accumulated size to prevent memory exhaustion
                    accumulated_size += len(line)
                    if accumulated_size > _MAX_STREAMING_SIZE_BYTES:
                        raise CPEError(
                            f"Streaming response exceeded {_MAX_STREAMING_SIZE_BYTES / 1024 / 1024:.0f}MB limit"
                        )
            return chunks
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
    Ollama API doesn't provide tool call IDs, so we generate synthetic IDs (call_0, call_1, ...)
    to maintain order-based mapping for tool results.
    """
    message = data.get("message", {})
    content = message.get("content") or ""
    tool_calls: list[ToolUseCall] = []

    # Parse tool_calls from official format: message.tool_calls[]
    # Timestamp-based prefix for globally unique synthetic IDs (avoids collisions across adapter instances)
    timestamp_ms = int(time.time() * 1000)
    for tc_index, tc in enumerate(message.get("tool_calls") or []):
        fn = tc.get("function", {})
        raw_args = fn.get("arguments", {})

        # Normalize: arguments may be dict or JSON string
        if isinstance(raw_args, str):
            try:
                raw_args = json.loads(raw_args)
            except (json.JSONDecodeError, ValueError):
                raw_args = {}

        parsed_input = raw_args if isinstance(raw_args, dict) else {}
        # Generate globally unique synthetic ID: timestamp + index
        # Avoids collisions when multiple adapter instances generate IDs in same second
        synthetic_id = f"call_{timestamp_ms}_{tc_index}"
        tool_calls.append(ToolUseCall(
            id=synthetic_id,
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


def _parse_streaming_response(chunks: list[dict[str, Any]]) -> CPEResponse:
    """Parse accumulated streaming chunks into CPEResponse.

    Streaming format: each chunk is a partial message update.
    Accumulates content and tool calls across chunks.
    Final chunk has done=True and contains usage metadata.
    """
    content = ""
    tool_calls: list[ToolUseCall] = []
    total_input_tokens = 0
    total_output_tokens = 0
    stop_reason = ""

    # Timestamp-based prefix for globally unique synthetic IDs
    timestamp_ms = int(time.time() * 1000)
    tc_index = 0  # Local counter within this streaming response
    for chunk in chunks:
        message = chunk.get("message", {})

        # Accumulate text content
        if "content" in message:
            content += message.get("content", "")

        # Process tool calls (may appear in multiple chunks)
        for tc in message.get("tool_calls") or []:
            fn = tc.get("function", {})
            raw_args = fn.get("arguments", {})

            # Normalize: arguments may be dict or JSON string
            if isinstance(raw_args, str):
                try:
                    raw_args = json.loads(raw_args)
                except (json.JSONDecodeError, ValueError):
                    raw_args = {}

            parsed_input = raw_args if isinstance(raw_args, dict) else {}
            # Generate globally unique synthetic ID: timestamp + index
            synthetic_id = f"call_{timestamp_ms}_{tc_index}"
            tool_calls.append(ToolUseCall(
                id=synthetic_id,
                tool=fn.get("name", ""),
                input=parsed_input,
            ))
            tc_index += 1

        # Extract usage and stop reason from final chunk
        if chunk.get("done"):
            total_input_tokens = int(chunk.get("prompt_eval_count", 0))
            total_output_tokens = int(chunk.get("eval_count", 0))
            stop_reason = chunk.get("done_reason", "")

    return CPEResponse(
        text=content,
        tool_use_calls=tool_calls,
        input_tokens=total_input_tokens,
        output_tokens=total_output_tokens,
        stop_reason=stop_reason,
    )
