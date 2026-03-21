"""
Google Gemini API adapter.  §6

Uses urllib.request (stdlib) — zero external dependencies.
API reference: https://ai.google.dev/api/generate-content
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.parse
from typing import Any

from .base import CPEAuthError, CPEResponse, ToolUseCall, _trunc, validate_invoke_inputs
from ._http import post_json

logger = logging.getLogger(__name__)

_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
_DEFAULT_MODEL = "gemini-2.0-flash"
_MAX_TOKENS = 8192


class GoogleAdapter:
    """CPEAdapter for Gemini via the Google AI generateContent API."""

    def __init__(self, api_key: str = "", model: str = _DEFAULT_MODEL) -> None:
        self._api_key = api_key or os.environ.get("GOOGLE_API_KEY", "")
        self._model = model
        # Track the last model turn's parts verbatim (required for thought_signature)
        self._last_model_parts: list[dict[str, Any]] = []

    def invoke(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> CPEResponse:
        # Validate inputs early
        validate_invoke_inputs(system, messages, tools)

        contents = _build_contents(messages, self._last_model_parts)

        payload: dict[str, Any] = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": contents,
            "generationConfig": {"maxOutputTokens": _MAX_TOKENS},
        }
        if tools:
            payload["tools"] = [{"function_declarations": [_convert_tool(t) for t in tools]}]
        raw = _post(self._api_key, self._model, payload)
        response, raw_model_parts = _parse_response(raw)
        self._last_model_parts = raw_model_parts
        return response

    def _reset_state(self) -> None:
        """Reset adapter state for fallback chain recovery.

        Clears cached model parts so next adapter doesn't inherit stale
        thought_signature state from a failed invocation.
        """
        self._last_model_parts = []


def _build_contents(
    messages: list[dict[str, Any]],
    last_model_parts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert chat_history to Gemini contents format.

    When an assistant turn had tool_use (content==""), the following user turn
    contains tool results in the format "[tool_name] {json}\\n[tool_name] {json}".
    We detect this pattern and emit functionResponse parts.

    For the LAST tool-use turn, we use last_model_parts verbatim to preserve
    thought_signature. For historical turns, we reconstruct minimal functionCall
    parts from the tool names extracted from the result lines.
    """
    contents: list[dict[str, Any]] = []

    # Find the last empty assistant turn index (for thought_signature preservation)
    last_tool_turn_idx = -1
    for j in range(len(messages) - 1, -1, -1):
        if messages[j]["role"] == "assistant" and not messages[j].get("content", ""):
            last_tool_turn_idx = j
            break

    i = 0
    while i < len(messages):
        msg = messages[i]
        role = msg["role"]
        content = msg.get("content", "")

        if role == "assistant":
            if not content:
                # Tool-use turn
                is_last = (i == last_tool_turn_idx)
                if is_last and last_model_parts:
                    # Preserve thought_signature for the last tool turn
                    contents.append({"role": "model", "parts": last_model_parts})
                else:
                    # Historical turn: reconstruct minimal functionCall parts by peeking
                    # at the following user turn to extract tool names
                    fc_parts: list[dict[str, Any]] = []
                    if i + 1 < len(messages):
                        next_results = _parse_tool_results(messages[i + 1].get("content", ""))
                        if next_results:
                            fc_parts = [
                                {"functionCall": {"name": name, "args": {}}}
                                for name, _ in next_results
                            ]
                    if fc_parts:
                        contents.append({"role": "model", "parts": fc_parts})
                    else:
                        contents.append({"role": "model", "parts": [{"text": ""}]})
            else:
                contents.append({"role": "model", "parts": [{"text": content}]})
            i += 1
            continue

        # user turn — check if it follows an empty assistant turn (tool result)
        if (role == "user" and i > 0
                and messages[i - 1]["role"] == "assistant"
                and not messages[i - 1].get("content", "")):
            tool_results = _parse_tool_results(content)
            if tool_results is not None:
                # Build functionResponse parts using extracted tool names
                # Names come from the results themselves — no dependency on last_function_calls
                parts: list[dict[str, Any]] = [
                    {
                        "functionResponse": {
                            "name": name,
                            "response": {"output": data},
                        }
                    }
                    for name, data in tool_results
                ]
                if parts:
                    contents.append({"role": "user", "parts": parts})
                    i += 1
                    continue
            else:
                logger.debug(
                    f"Could not parse tool results from user turn after empty assistant. "
                    f"Content preview: {content[:100]}"
                )

        contents.append({"role": "user", "parts": [{"text": content}]})
        i += 1

    return contents


def _parse_tool_results(text: str) -> list[tuple[str, dict[str, Any]]] | None:
    """Parse a tool result turn into a list of (tool_name, result_dict) pairs.

    Tool result turns have the format:
      [tool_name] {json}
      [tool_name] {json}

    Returns list of (name, data) tuples, or None if the text does not match
    the expected format. The tool name is extracted from the brackets.
    """
    if not text or not text.startswith("["):
        return None
    results: list[tuple[str, dict[str, Any]]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if not line.startswith("["):
            return None  # not a tool result format
        bracket_end = line.find("]")
        if bracket_end == -1:
            return None
        tool_name = line[1:bracket_end]
        json_part = line[bracket_end + 1:].strip()
        try:
            data = json.loads(json_part)
            if not isinstance(data, dict):
                return None
            results.append((tool_name, data))
        except (json.JSONDecodeError, ValueError):
            return None
    return results if results else None


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
    return post_json(
        url=url,
        headers={"Content-Type": "application/json"},
        payload=payload,
        provider="Google",
    )


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

def _parse_response(data: dict[str, Any]) -> tuple[CPEResponse, list[dict[str, Any]]]:
    candidates = data.get("candidates", [])
    candidate = candidates[0] if candidates else {}
    content = candidate.get("content", {})
    text = ""
    tool_calls: list[ToolUseCall] = []
    raw_model_parts: list[dict[str, Any]] = list(content.get("parts", []))
    # Timestamp-based prefix for globally unique synthetic IDs (avoids collisions across adapter instances)
    timestamp_ms = int(time.time() * 1000)
    for fc_index, part in enumerate(raw_model_parts):
        if "text" in part and not part.get("thought"):
            text = part["text"]
        elif "functionCall" in part:
            fc = part["functionCall"]
            # Generate globally unique synthetic ID: timestamp + index
            # Avoids collisions when multiple adapter instances generate IDs in same second
            synthetic_id = f"call_{timestamp_ms}_{fc_index}"
            tool_calls.append(ToolUseCall(
                id=synthetic_id,
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
    ), raw_model_parts
