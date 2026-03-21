"""
Debug and validation tests for Ollama adapter improvements (2026-03-20).

Tests verify:
1. Tool call parsing from official Ollama API format
2. Argument normalization (dict vs JSON string)
3. Compatibility with expected response structure
4. No spurious fallback parsing
"""

import json
import pytest
from fcp_base.cpe.ollama import _parse_response, _convert_tool


class TestOllamaToolCallParsing:
    """Verify tool_calls parsing matches official Ollama API format."""

    def test_tool_calls_with_dict_arguments(self):
        """Tool calls with arguments as dict (official format)."""
        response_data = {
            "model": "qwen:7b",
            "message": {
                "role": "assistant",
                "content": "I'll check the weather for you.",
                "tool_calls": [
                    {
                        "function": {
                            "name": "get_weather",
                            "arguments": {"location": "San Francisco", "unit": "celsius"}
                        }
                    }
                ]
            },
            "done": True,
            "done_reason": "stop",
            "prompt_eval_count": 100,
            "eval_count": 50,
        }

        result = _parse_response(response_data)

        assert len(result.tool_use_calls) == 1
        assert result.tool_use_calls[0].tool == "get_weather"
        assert result.tool_use_calls[0].input == {"location": "San Francisco", "unit": "celsius"}
        assert result.text == "I'll check the weather for you."
        assert result.input_tokens == 100
        assert result.output_tokens == 50

    def test_tool_calls_with_json_string_arguments(self):
        """Tool calls with arguments as JSON string (alternate format)."""
        response_data = {
            "model": "qwen:7b",
            "message": {
                "role": "assistant",
                "content": "Fetching data...",
                "tool_calls": [
                    {
                        "function": {
                            "name": "search_db",
                            "arguments": '{"query": "user info", "limit": 10}'
                        }
                    }
                ]
            },
            "done": True,
            "done_reason": "stop",
            "prompt_eval_count": 80,
            "eval_count": 30,
        }

        result = _parse_response(response_data)

        assert len(result.tool_use_calls) == 1
        assert result.tool_use_calls[0].tool == "search_db"
        assert result.tool_use_calls[0].input == {"query": "user info", "limit": 10}
        assert result.text == "Fetching data..."

    def test_multiple_tool_calls(self):
        """Multiple tool calls in single response."""
        response_data = {
            "model": "qwen:7b",
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": "fcp_exec",
                            "arguments": {"command": "ls -la"}
                        }
                    },
                    {
                        "function": {
                            "name": "fcp_mil",
                            "arguments": '{"action": "recall", "type": "episodic"}'
                        }
                    },
                ]
            },
            "done": True,
            "done_reason": "tool_calls",
            "prompt_eval_count": 120,
            "eval_count": 25,
        }

        result = _parse_response(response_data)

        assert len(result.tool_use_calls) == 2
        assert result.tool_use_calls[0].tool == "fcp_exec"
        assert result.tool_use_calls[0].input == {"command": "ls -la"}
        assert result.tool_use_calls[1].tool == "fcp_mil"
        assert result.tool_use_calls[1].input == {"action": "recall", "type": "episodic"}
        assert result.text == ""

    def test_no_tool_calls_just_text(self):
        """Response with text but no tool calls."""
        response_data = {
            "model": "qwen:7b",
            "message": {
                "role": "assistant",
                "content": "The weather today is sunny with a high of 25°C.",
                "tool_calls": []
            },
            "done": True,
            "done_reason": "stop",
            "prompt_eval_count": 50,
            "eval_count": 20,
        }

        result = _parse_response(response_data)

        assert len(result.tool_use_calls) == 0
        assert result.text == "The weather today is sunny with a high of 25°C."

    def test_malformed_json_arguments_fallback_to_empty(self):
        """Malformed JSON in arguments → fallback to {}."""
        response_data = {
            "model": "qwen:7b",
            "message": {
                "role": "assistant",
                "content": "Processing...",
                "tool_calls": [
                    {
                        "function": {
                            "name": "process",
                            "arguments": "not valid json"
                        }
                    }
                ]
            },
            "done": True,
            "done_reason": "stop",
            "prompt_eval_count": 60,
            "eval_count": 15,
        }

        result = _parse_response(response_data)

        assert len(result.tool_use_calls) == 1
        assert result.tool_use_calls[0].tool == "process"
        assert result.tool_use_calls[0].input == {}  # Fallback to empty dict

    def test_empty_tool_calls_array(self):
        """Empty tool_calls array in message."""
        response_data = {
            "model": "qwen:7b",
            "message": {
                "role": "assistant",
                "content": "No tools needed.",
                "tool_calls": []
            },
            "done": True,
            "done_reason": "stop",
            "prompt_eval_count": 40,
            "eval_count": 10,
        }

        result = _parse_response(response_data)

        assert len(result.tool_use_calls) == 0
        assert result.text == "No tools needed."

    def test_missing_tool_calls_field(self):
        """Response without tool_calls field (should not error)."""
        response_data = {
            "model": "qwen:7b",
            "message": {
                "role": "assistant",
                "content": "Response without tool_calls field."
            },
            "done": True,
            "done_reason": "stop",
            "prompt_eval_count": 30,
            "eval_count": 8,
        }

        result = _parse_response(response_data)

        assert len(result.tool_use_calls) == 0
        assert result.text == "Response without tool_calls field."

    def test_missing_message_field(self):
        """Response without message field (edge case)."""
        response_data = {
            "model": "qwen:7b",
            "done": True,
            "done_reason": "stop",
            "prompt_eval_count": 20,
            "eval_count": 5,
        }

        result = _parse_response(response_data)

        assert len(result.tool_use_calls) == 0
        assert result.text == ""


class TestToolConversion:
    """Verify FCP tool format → Ollama format conversion."""

    def test_convert_fcp_tool_to_ollama(self):
        """Convert FCP tool declaration to Ollama format."""
        fcp_tool = {
            "name": "fcp_exec",
            "description": "Execute shell commands",
            "input_schema": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Command to execute"}
                },
                "required": ["command"]
            }
        }

        result = _convert_tool(fcp_tool)

        assert result["type"] == "function"
        assert result["function"]["name"] == "fcp_exec"
        assert result["function"]["description"] == "Execute shell commands"
        assert result["function"]["parameters"] == fcp_tool["input_schema"]

    def test_convert_tool_minimal(self):
        """Convert tool with minimal fields."""
        fcp_tool = {
            "name": "simple_tool",
            "description": "A simple tool"
        }

        result = _convert_tool(fcp_tool)

        assert result["type"] == "function"
        assert result["function"]["name"] == "simple_tool"
        assert result["function"]["description"] == "A simple tool"
        assert result["function"]["parameters"] == {"type": "object", "properties": {}}


class TestOllamaRegressions:
    """Regression tests to ensure fixes don't break existing behavior."""

    def test_parsing_still_works_with_old_format(self):
        """Ensure backward compatibility if old quirks still appear."""
        # This tests the new, cleaner parsing without quirk fallback
        response_data = {
            "model": "mistral",
            "message": {
                "role": "assistant",
                "content": "Weather status",
                "tool_calls": [
                    {
                        "function": {
                            "name": "weather",
                            "arguments": {"location": "NYC"}
                        }
                    }
                ]
            },
            "done": True,
            "done_reason": "stop",
            "prompt_eval_count": 45,
            "eval_count": 12,
        }

        result = _parse_response(response_data)

        # Should parse correctly using official format
        assert len(result.tool_use_calls) == 1
        assert result.tool_use_calls[0].tool == "weather"
        assert result.input_tokens == 45
        assert result.output_tokens == 12
        assert result.stop_reason == "stop"
