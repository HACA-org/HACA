"""
CPE Adapter Unit Tests — Comprehensive test coverage for all 5 adapters.

Tests cover:
- Tool call parsing (single, multiple, with/without text)
- Malformed response handling
- Token counting accuracy
- Error handling
- Message format validation

Date: 2026-03-21
"""

import json
import os
import pytest
from fcp_base.cpe.base import CPEResponse, ToolUseCall
from fcp_base.cpe.anthropic import _parse_response as anthropic_parse
from fcp_base.cpe.openai import _parse_response as openai_parse
from fcp_base.cpe.google import _parse_response as google_parse
from fcp_base.cpe.ollama import _parse_response as ollama_parse
from fcp_base.cpe.models import (
    get_default_model,
    get_api_version,
    get_max_tokens,
    list_models,
    supports_feature,
)


class TestAnthropicParsing:
    """Test Anthropic Messages API response parsing."""

    def test_text_only_response(self):
        """Text response without tool calls."""
        data = {
            "content": [
                {"type": "text", "text": "Hello, how can I help?"}
            ],
            "usage": {"input_tokens": 100, "output_tokens": 50},
            "stop_reason": "end_turn",
        }
        result = anthropic_parse(data)
        assert result.text == "Hello, how can I help?"
        assert len(result.tool_use_calls) == 0
        assert result.input_tokens == 100
        assert result.output_tokens == 50

    def test_single_tool_call(self):
        """Single tool call with text."""
        data = {
            "content": [
                {"type": "text", "text": "I'll execute that for you."},
                {
                    "type": "tool_use",
                    "id": "call_123",
                    "name": "fcp_exec",
                    "input": {"command": "ls -la"}
                }
            ],
            "usage": {"input_tokens": 120, "output_tokens": 75},
            "stop_reason": "tool_use",
        }
        result = anthropic_parse(data)
        assert result.text == "I'll execute that for you."
        assert len(result.tool_use_calls) == 1
        assert result.tool_use_calls[0].id == "call_123"
        assert result.tool_use_calls[0].tool == "fcp_exec"
        assert result.tool_use_calls[0].input == {"command": "ls -la"}

    def test_multiple_tool_calls(self):
        """Multiple tool calls in single response."""
        data = {
            "content": [
                {
                    "type": "tool_use",
                    "id": "call_1",
                    "name": "fcp_exec",
                    "input": {"command": "pwd"}
                },
                {
                    "type": "tool_use",
                    "id": "call_2",
                    "name": "fcp_mil",
                    "input": {"action": "recall"}
                },
            ],
            "usage": {"input_tokens": 100, "output_tokens": 60},
            "stop_reason": "tool_use",
        }
        result = anthropic_parse(data)
        assert len(result.tool_use_calls) == 2
        assert result.tool_use_calls[0].tool == "fcp_exec"
        assert result.tool_use_calls[1].tool == "fcp_mil"
        assert result.text == ""

    def test_tool_call_without_text(self):
        """Tool call without text content."""
        data = {
            "content": [
                {
                    "type": "tool_use",
                    "id": "call_x",
                    "name": "test_tool",
                    "input": {"param": "value"}
                }
            ],
            "usage": {"input_tokens": 50, "output_tokens": 25},
            "stop_reason": "tool_use",
        }
        result = anthropic_parse(data)
        assert result.text == ""
        assert len(result.tool_use_calls) == 1

    def test_empty_response(self):
        """Empty content array."""
        data = {
            "content": [],
            "usage": {"input_tokens": 10, "output_tokens": 5},
            "stop_reason": "end_turn",
        }
        result = anthropic_parse(data)
        assert result.text == ""
        assert len(result.tool_use_calls) == 0


class TestOpenAIParsing:
    """Test OpenAI Chat Completions API response parsing."""

    def test_text_only_response(self):
        """Text response without tool calls."""
        data = {
            "choices": [{
                "message": {
                    "content": "Hello, how can I help?",
                    "tool_calls": None,
                },
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50},
        }
        result = openai_parse(data)
        assert result.text == "Hello, how can I help?"
        assert len(result.tool_use_calls) == 0

    def test_single_tool_call(self):
        """Single tool call."""
        data = {
            "choices": [{
                "message": {
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_abc123",
                            "function": {
                                "name": "fcp_exec",
                                "arguments": '{"command": "ls"}'
                            },
                            "type": "function",
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }],
            "usage": {"prompt_tokens": 120, "completion_tokens": 75},
        }
        result = openai_parse(data)
        assert len(result.tool_use_calls) == 1
        assert result.tool_use_calls[0].id == "call_abc123"
        assert result.tool_use_calls[0].tool == "fcp_exec"
        assert result.tool_use_calls[0].input == {"command": "ls"}

    def test_tool_call_with_dict_arguments(self):
        """Tool call where arguments are already a dict (not JSON string)."""
        data = {
            "choices": [{
                "message": {
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_dict",
                            "function": {
                                "name": "test_tool",
                                "arguments": '{"key": "value", "nested": {"a": 1}}'
                            },
                            "type": "function",
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50},
        }
        result = openai_parse(data)
        assert result.tool_use_calls[0].input == {"key": "value", "nested": {"a": 1}}

    def test_malformed_json_arguments(self):
        """Malformed JSON arguments should fallback to empty dict."""
        data = {
            "choices": [{
                "message": {
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_bad",
                            "function": {
                                "name": "broken_tool",
                                "arguments": "not valid json"
                            },
                            "type": "function",
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50},
        }
        result = openai_parse(data)
        assert result.tool_use_calls[0].input == {}

    def test_multiple_tool_calls(self):
        """Multiple parallel tool calls."""
        data = {
            "choices": [{
                "message": {
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "function": {
                                "name": "tool_a",
                                "arguments": '{}'
                            },
                        },
                        {
                            "id": "call_2",
                            "function": {
                                "name": "tool_b",
                                "arguments": '{"x": 1}'
                            },
                        },
                    ],
                },
                "finish_reason": "tool_calls",
            }],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50},
        }
        result = openai_parse(data)
        assert len(result.tool_use_calls) == 2
        assert result.tool_use_calls[0].tool == "tool_a"
        assert result.tool_use_calls[1].tool == "tool_b"

    def test_mixed_content_and_tool_calls(self):
        """Text content with tool calls."""
        data = {
            "choices": [{
                "message": {
                    "content": "Let me help with that.",
                    "tool_calls": [
                        {
                            "id": "call_mix",
                            "function": {
                                "name": "helper",
                                "arguments": '{}'
                            },
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50},
        }
        result = openai_parse(data)
        assert result.text == "Let me help with that."
        assert len(result.tool_use_calls) == 1


class TestGoogleParsing:
    """Test Google Gemini API response parsing."""

    def test_text_only_response(self):
        """Text response without tool calls."""
        data = {
            "candidates": [{
                "content": {
                    "parts": [
                        {"text": "Hello, how can I help?"}
                    ]
                },
                "finishReason": "STOP",
            }],
            "usageMetadata": {
                "promptTokenCount": 100,
                "candidatesTokenCount": 50,
            },
        }
        result, _, _ = google_parse(data)
        assert result.text == "Hello, how can I help?"
        assert len(result.tool_use_calls) == 0

    def test_single_tool_call(self):
        """Single tool call with synthetic ID generation."""
        data = {
            "candidates": [{
                "content": {
                    "parts": [
                        {
                            "functionCall": {
                                "name": "fcp_exec",
                                "args": {"command": "ls"}
                            }
                        }
                    ]
                },
                "finishReason": "TOOL_CALL",
            }],
            "usageMetadata": {
                "promptTokenCount": 100,
                "candidatesTokenCount": 50,
            },
        }
        result, _, _ = google_parse(data)
        assert len(result.tool_use_calls) == 1
        assert result.tool_use_calls[0].id == "call_0"  # Synthetic ID
        assert result.tool_use_calls[0].tool == "fcp_exec"
        assert result.tool_use_calls[0].input == {"command": "ls"}

    def test_multiple_tool_calls_get_sequential_ids(self):
        """Multiple tool calls get sequential synthetic IDs."""
        data = {
            "candidates": [{
                "content": {
                    "parts": [
                        {
                            "functionCall": {
                                "name": "tool_a",
                                "args": {}
                            }
                        },
                        {
                            "functionCall": {
                                "name": "tool_b",
                                "args": {"x": 1}
                            }
                        },
                    ]
                },
                "finishReason": "TOOL_CALL",
            }],
            "usageMetadata": {
                "promptTokenCount": 100,
                "candidatesTokenCount": 50,
            },
        }
        result, _, _ = google_parse(data)
        assert len(result.tool_use_calls) == 2
        assert result.tool_use_calls[0].id == "call_0"
        assert result.tool_use_calls[1].id == "call_1"

    def test_mixed_content_and_tool_calls(self):
        """Text with tool calls."""
        data = {
            "candidates": [{
                "content": {
                    "parts": [
                        {"text": "Processing your request..."},
                        {
                            "functionCall": {
                                "name": "processor",
                                "args": {"input": "data"}
                            }
                        },
                    ]
                },
                "finishReason": "TOOL_CALL",
            }],
            "usageMetadata": {
                "promptTokenCount": 100,
                "candidatesTokenCount": 50,
            },
        }
        result, _, _ = google_parse(data)
        assert result.text == "Processing your request..."
        assert len(result.tool_use_calls) == 1
        assert result.tool_use_calls[0].tool == "processor"

    def test_empty_response(self):
        """Empty response."""
        data = {
            "candidates": [{
                "content": {"parts": []},
                "finishReason": "STOP",
            }],
            "usageMetadata": {
                "promptTokenCount": 10,
                "candidatesTokenCount": 5,
            },
        }
        result, _, _ = google_parse(data)
        assert result.text == ""
        assert len(result.tool_use_calls) == 0


class TestEdgeCases:
    """Edge case tests across adapters."""

    def test_missing_usage_data(self):
        """Missing usage metadata should default to 0."""
        anthropic_data = {
            "content": [{"type": "text", "text": "Hello"}],
            # Missing usage field
            "stop_reason": "end_turn",
        }
        result = anthropic_parse(anthropic_data)
        assert result.input_tokens == 0
        assert result.output_tokens == 0

    def test_missing_content_array(self):
        """Missing content array should be handled gracefully."""
        anthropic_data = {
            # Missing content field
            "usage": {"input_tokens": 50, "output_tokens": 25},
            "stop_reason": "end_turn",
        }
        result = anthropic_parse(anthropic_data)
        assert result.text == ""
        assert len(result.tool_use_calls) == 0

    def test_null_text_content(self):
        """Null text content should be handled."""
        openai_data = {
            "choices": [{
                "message": {
                    "content": None,
                    "tool_calls": [],
                },
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 50, "completion_tokens": 25},
        }
        result = openai_parse(openai_data)
        assert result.text == ""


class TestModelRegistry:
    """Test CPE model registry and configuration."""

    def test_get_default_model_anthropic(self):
        """Default model for Anthropic."""
        model = get_default_model("anthropic")
        assert model == "claude-opus-4-6"

    def test_get_default_model_openai(self):
        """Default model for OpenAI."""
        model = get_default_model("openai")
        assert model == "gpt-4o"

    def test_get_default_model_google(self):
        """Default model for Google."""
        model = get_default_model("google")
        assert model == "gemini-2.0-flash"

    def test_get_default_model_ollama(self):
        """Default model for Ollama."""
        model = get_default_model("ollama")
        assert model == "llama3.2"

    def test_get_api_version_anthropic(self):
        """API version for Anthropic."""
        version = get_api_version("anthropic")
        assert version == "2024-06-15"

    def test_get_max_tokens(self):
        """Max tokens per adapter."""
        assert get_max_tokens("anthropic") == 8192
        assert get_max_tokens("openai") == 8192
        assert get_max_tokens("google") == 8192
        assert get_max_tokens("ollama") == 8192

    def test_list_models_anthropic(self):
        """List Anthropic models."""
        models = list_models("anthropic")
        assert len(models) > 0
        assert "claude-opus-4-6" in models

    def test_supports_feature_openai_caching(self):
        """OpenAI supports prompt caching."""
        assert supports_feature("openai", "prompt_caching") is True

    def test_supports_feature_ollama_streaming(self):
        """Ollama supports streaming."""
        assert supports_feature("ollama", "streaming") is True

    def test_supports_feature_google_thinking(self):
        """Google supports thinking."""
        assert supports_feature("google", "thinking") is True

    def test_env_override_model(self):
        """Environment variable can override default model."""
        os.environ["OPENAI_MODEL"] = "gpt-4o-mini"
        model = get_default_model("openai")
        assert model == "gpt-4o-mini"
        # Clean up
        del os.environ["OPENAI_MODEL"]

    def test_unknown_adapter_returns_empty(self):
        """Unknown adapter returns empty string."""
        model = get_default_model("unknown_adapter")
        assert model == ""


class TestOpenAIPromptCaching:
    """Test OpenAI prompt caching logic."""

    def test_first_invoke_includes_system_with_cache_control(self):
        """First invoke should include system message with cache_control."""
        from fcp_base.cpe.openai import _build_messages_with_caching

        system = "You are a helpful assistant."
        messages = [{"role": "user", "content": "Hello"}]

        result = _build_messages_with_caching(
            system=system,
            messages=messages,
            base_url="https://api.openai.com/v1",
            system_cached=False,
            cached_system="",
        )

        assert len(result) == 2
        assert result[0]["role"] == "system"
        assert result[0]["content"] == system
        assert result[0]["cache_control"] == {"type": "ephemeral"}
        assert result[1] == messages[0]

    def test_subsequent_invoke_omits_system_if_unchanged(self):
        """Subsequent invoke should omit system message if unchanged."""
        from fcp_base.cpe.openai import _build_messages_with_caching

        system = "You are a helpful assistant."
        messages = [{"role": "user", "content": "What is 2+2?"}]

        result = _build_messages_with_caching(
            system=system,
            messages=messages,
            base_url="https://api.openai.com/v1",
            system_cached=True,
            cached_system=system,  # same as current system
        )

        # System message should be omitted (cached)
        assert len(result) == 1
        assert result[0] == messages[0]

    def test_system_change_resends_with_cache_control(self):
        """If system message changes, resend it with cache_control."""
        from fcp_base.cpe.openai import _build_messages_with_caching

        old_system = "You are a helpful assistant."
        new_system = "You are a strict code reviewer."
        messages = [{"role": "user", "content": "Review this code."}]

        result = _build_messages_with_caching(
            system=new_system,
            messages=messages,
            base_url="https://api.openai.com/v1",
            system_cached=True,
            cached_system=old_system,  # different from new_system
        )

        assert len(result) == 2
        assert result[0]["role"] == "system"
        assert result[0]["content"] == new_system
        assert result[0]["cache_control"] == {"type": "ephemeral"}
        assert result[1] == messages[0]

    def test_compatible_endpoint_always_includes_system(self):
        """Compatible endpoints should always include system (no caching)."""
        from fcp_base.cpe.openai import _build_messages_with_caching

        system = "You are helpful."
        messages = [{"role": "user", "content": "Hi"}]

        # Even with system_cached=True, compatible endpoint includes system
        result = _build_messages_with_caching(
            system=system,
            messages=messages,
            base_url="http://localhost:8000/v1",  # compatible endpoint
            system_cached=True,
            cached_system=system,
        )

        assert len(result) == 2
        assert result[0]["role"] == "system"
        assert result[0]["content"] == system
        assert "cache_control" not in result[0]


class TestOllamaStreaming:
    """Test Ollama streaming mode."""

    def test_streaming_accumulates_content(self):
        """Streaming chunks accumulate content across multiple chunks."""
        from fcp_base.cpe.ollama import _parse_streaming_response

        chunks = [
            {
                "message": {"content": "Hello, "},
                "done": False,
            },
            {
                "message": {"content": "how can I help?"},
                "done": False,
            },
            {
                "message": {"content": ""},
                "done": True,
                "prompt_eval_count": 100,
                "eval_count": 50,
                "done_reason": "stop",
            },
        ]

        result = _parse_streaming_response(chunks)
        assert result.text == "Hello, how can I help?"
        assert result.input_tokens == 100
        assert result.output_tokens == 50
        assert result.stop_reason == "stop"

    def test_streaming_with_tool_calls(self):
        """Streaming can extract tool calls from chunks."""
        from fcp_base.cpe.ollama import _parse_streaming_response

        chunks = [
            {
                "message": {"content": "I'll help with that."},
                "done": False,
            },
            {
                "message": {
                    "tool_calls": [
                        {
                            "function": {
                                "name": "fcp_exec",
                                "arguments": {"command": "ls"}
                            }
                        }
                    ]
                },
                "done": False,
            },
            {
                "message": {"content": ""},
                "done": True,
                "prompt_eval_count": 120,
                "eval_count": 75,
                "done_reason": "tool_calls",
            },
        ]

        result = _parse_streaming_response(chunks)
        assert result.text == "I'll help with that."
        assert len(result.tool_use_calls) == 1
        assert result.tool_use_calls[0].id == "call_0"
        assert result.tool_use_calls[0].tool == "fcp_exec"

    def test_streaming_multiple_tool_calls_sequential_ids(self):
        """Streaming extracts multiple tool calls with sequential IDs."""
        from fcp_base.cpe.ollama import _parse_streaming_response

        chunks = [
            {
                "message": {
                    "tool_calls": [
                        {
                            "function": {
                                "name": "tool_a",
                                "arguments": {}
                            }
                        }
                    ]
                },
                "done": False,
            },
            {
                "message": {
                    "tool_calls": [
                        {
                            "function": {
                                "name": "tool_b",
                                "arguments": {"x": 1}
                            }
                        }
                    ]
                },
                "done": False,
            },
            {
                "message": {"content": ""},
                "done": True,
                "prompt_eval_count": 100,
                "eval_count": 50,
                "done_reason": "tool_calls",
            },
        ]

        result = _parse_streaming_response(chunks)
        assert len(result.tool_use_calls) == 2
        assert result.tool_use_calls[0].id == "call_0"
        assert result.tool_use_calls[1].id == "call_1"


class TestOllamaParsing:
    """Test Ollama API response parsing."""

    def test_text_only_response(self):
        """Text response without tool calls."""
        data = {
            "message": {
                "content": "Hello, how can I help?",
                "tool_calls": None,
            },
            "prompt_eval_count": 100,
            "eval_count": 50,
            "done_reason": "stop",
        }
        result = ollama_parse(data)
        assert result.text == "Hello, how can I help?"
        assert len(result.tool_use_calls) == 0
        assert result.input_tokens == 100
        assert result.output_tokens == 50

    def test_single_tool_call(self):
        """Single tool call with synthetic ID."""
        data = {
            "message": {
                "content": "I'll execute that for you.",
                "tool_calls": [
                    {
                        "function": {
                            "name": "fcp_exec",
                            "arguments": {"command": "ls -la"}
                        }
                    }
                ],
            },
            "prompt_eval_count": 120,
            "eval_count": 75,
            "done_reason": "tool_calls",
        }
        result = ollama_parse(data)
        assert result.text == "I'll execute that for you."
        assert len(result.tool_use_calls) == 1
        assert result.tool_use_calls[0].id == "call_0"  # Synthetic ID
        assert result.tool_use_calls[0].tool == "fcp_exec"
        assert result.tool_use_calls[0].input == {"command": "ls -la"}

    def test_tool_call_with_json_string_arguments(self):
        """Tool call where arguments are a JSON string (not dict)."""
        data = {
            "message": {
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": "test_tool",
                            "arguments": '{"key": "value", "nested": {"a": 1}}'
                        }
                    }
                ],
            },
            "prompt_eval_count": 100,
            "eval_count": 50,
            "done_reason": "tool_calls",
        }
        result = ollama_parse(data)
        assert result.tool_use_calls[0].input == {"key": "value", "nested": {"a": 1}}

    def test_multiple_tool_calls_get_sequential_ids(self):
        """Multiple tool calls get sequential synthetic IDs."""
        data = {
            "message": {
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": "tool_a",
                            "arguments": {}
                        }
                    },
                    {
                        "function": {
                            "name": "tool_b",
                            "arguments": {"x": 1}
                        }
                    },
                ],
            },
            "prompt_eval_count": 100,
            "eval_count": 50,
            "done_reason": "tool_calls",
        }
        result = ollama_parse(data)
        assert len(result.tool_use_calls) == 2
        assert result.tool_use_calls[0].id == "call_0"
        assert result.tool_use_calls[1].id == "call_1"
        assert result.tool_use_calls[0].tool == "tool_a"
        assert result.tool_use_calls[1].tool == "tool_b"

    def test_empty_response(self):
        """Empty response."""
        data = {
            "message": {"content": "", "tool_calls": None},
            "prompt_eval_count": 10,
            "eval_count": 5,
            "done_reason": "stop",
        }
        result = ollama_parse(data)
        assert result.text == ""
        assert len(result.tool_use_calls) == 0
