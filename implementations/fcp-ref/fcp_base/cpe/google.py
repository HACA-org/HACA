"""
Google Gemini API adapter.  §6

Uses urllib.request (stdlib) — zero external dependencies.
API reference: https://ai.google.dev/api/generate-content
"""

from __future__ import annotations

import json
import os
import time
import urllib.parse
from typing import Any

from .base import CPEAuthError, CPEResponse, ToolUseCall, _trunc
from ._http import post_json

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
        # Track only the functionCall parts for building functionResponse
        self._last_function_calls: list[dict[str, Any]] = []

    def invoke(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> CPEResponse:
        contents = _build_contents(messages, self._last_model_parts, self._last_function_calls)

        payload: dict[str, Any] = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": contents,
            "generationConfig": {"maxOutputTokens": _MAX_TOKENS},
        }
        if tools:
            payload["tools"] = [{"function_declarations": [_convert_tool(t) for t in tools]}]
        raw = _post(self._api_key, self._model, payload)
        response, raw_model_parts, raw_fc_parts = _parse_response(raw)
        self._last_model_parts = raw_model_parts
        self._last_function_calls = raw_fc_parts
        return response


def _build_contents(
    messages: list[dict[str, Any]],
    last_model_parts: list[dict[str, Any]],
    last_function_calls: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert chat_history to Gemini contents format.

    When an assistant turn had tool_use (content==""), the following user turn
    contains tool results in the format "[tool_name] {json}\\n[tool_name] {json}".
    We detect this pattern and emit functionResponse parts, using
    last_function_calls to map results to function names.
    """
    contents: list[dict[str, Any]] = []
    i = 0
    while i < len(messages):
        msg = messages[i]
        role = msg["role"]
        content = msg.get("content", "")

        if role == "assistant":
            if not content:
                # Tool-use turn — emit verbatim model parts (preserves thought_signature)
                if last_model_parts:
                    contents.append({"role": "model", "parts": last_model_parts})
                else:
                    contents.append({"role": "model", "parts": [{"text": ""}]})
            else:
                contents.append({"role": "model", "parts": [{"text": content}]})
            i += 1
            continue

        # user turn — check if it follows an empty assistant turn (tool result)
        if (role == "user" and last_function_calls and i > 0
                and messages[i - 1]["role"] == "assistant"
                and not messages[i - 1].get("content", "")):
            tool_results = _parse_tool_results(content)
            if tool_results is not None:
                parts: list[dict[str, Any]] = []
                for j, fc in enumerate(last_function_calls):
                    resp = tool_results[j] if j < len(tool_results) else {}
                    parts.append({
                        "functionResponse": {
                            "name": fc["functionCall"]["name"],
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


def _parse_tool_results(text: str) -> list[dict[str, Any]] | None:
    """Parse a tool result turn from chat_history into a list of result dicts.

    Tool result turns have the format:
      [tool_name] {json}
      [tool_name] {json}

    Returns a list of parsed dicts (one per line), or None if the text does
    not look like a tool result turn.
    """
    if not text or not text.startswith("["):
        return None
    results: list[dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if not line.startswith("["):
            return None  # not a tool result format
        # extract: "[tool_name] {json}"
        bracket_end = line.find("]")
        if bracket_end == -1:
            return None
        json_part = line[bracket_end + 1:].strip()
        try:
            data = json.loads(json_part)
            if not isinstance(data, dict):
                return None
            results.append(data)
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

def _parse_response(data: dict[str, Any]) -> tuple[CPEResponse, list[dict[str, Any]], list[dict[str, Any]]]:
    candidates = data.get("candidates", [])
    candidate = candidates[0] if candidates else {}
    content = candidate.get("content", {})
    text = ""
    tool_calls: list[ToolUseCall] = []
    raw_model_parts: list[dict[str, Any]] = list(content.get("parts", []))
    raw_fc_parts: list[dict[str, Any]] = []
    # Timestamp-based prefix for globally unique synthetic IDs (avoids collisions across adapter instances)
    timestamp_ms = int(time.time() * 1000)
    for fc_index, part in enumerate(raw_model_parts):
        if "text" in part and not part.get("thought"):
            text = part["text"]
        elif "functionCall" in part:
            raw_fc_parts.append(part)
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
    ), raw_model_parts, raw_fc_parts
