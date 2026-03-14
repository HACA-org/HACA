"""
CPE Adapter interface.

Defines CPEResponse (output) and the CPEAdapter Protocol that all adapters implement.

Adapters receive a pre-built (system, messages, tools) triple — the session loop
owns context assembly and chat history accumulation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Topology
# ---------------------------------------------------------------------------

class Topology:
    TRANSPARENT = "transparent"
    OPAQUE      = "opaque"


# ---------------------------------------------------------------------------
# Response (output from invoke)
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class ToolUseCall:
    """A single tool_use call emitted by the CPE."""
    id:    str
    tool:  str              # "fcp_exec" | "fcp_mil" | "fcp_sil"
    input: dict[str, Any]   # raw input object from the API response


@dataclass(slots=True)
class CPEResponse:
    """Normalised response from any CPE adapter."""
    text:           str                 # final narrative text (may be empty)
    tool_use_calls: list[ToolUseCall]
    input_tokens:   int
    output_tokens:  int
    stop_reason:    str                 # "end_turn" | "tool_use" | "max_tokens" | …


# ---------------------------------------------------------------------------
# CPEAdapter Protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class CPEAdapter(Protocol):
    """Uniform interface over all CPE backends.

    invoke(system, messages, tools) — system is fixed for the session lifetime;
    messages is the growing chat history; tools are the FCP tool declarations.
    """

    def invoke(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> CPEResponse:
        """Send context to the CPE and return a normalised response.

        Raises CPEError on network failure, authentication error, or
        any non-retryable API error.  Retry logic lives in the session loop.
        """
        ...  # pragma: no cover


# ---------------------------------------------------------------------------
# Mutable adapter reference (allows mid-session model swap)
# ---------------------------------------------------------------------------

class AdapterRef:
    """Thin wrapper so the session loop and operator handler share the same adapter."""
    def __init__(self, adapter: CPEAdapter) -> None:
        self.current = adapter


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _trunc(s: str, n: int = 200) -> str:
    """Return first *n* characters of *s* (Pyre2-safe truncation helper)."""
    import itertools
    return "".join(itertools.islice(s, n))


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class CPEError(Exception):
    """Raised by adapters on non-retryable CPE failures."""


class CPEAuthError(CPEError):
    """API key missing or rejected."""


class CPERateLimitError(CPEError):
    """Rate limit or quota exceeded — caller may retry after backoff."""


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def make_adapter(backend: str, api_key: str, model: str) -> CPEAdapter:
    """Instantiate the correct adapter for *backend*.

    backend must match a value from StructuralBaseline.cpe.backend.
    Raises ValueError for unknown backends.
    """
    if backend == "anthropic":
        from .anthropic import AnthropicAdapter
        return AnthropicAdapter(api_key=api_key, model=model)
    if backend in ("openai", "openai-compatible"):
        from .openai import OpenAIAdapter
        return OpenAIAdapter(api_key=api_key, model=model)
    if backend == "google":
        from .google import GoogleAdapter
        return GoogleAdapter(api_key=api_key, model=model)
    if backend == "ollama":
        from .ollama import OllamaAdapter
        return OllamaAdapter(api_key="", model=model)
    raise ValueError(f"Unknown CPE backend: {backend!r}")


def detect_adapter(model: str = "") -> CPEAdapter:
    """Auto-detect the best available CPE adapter.

    Priority: ANTHROPIC_API_KEY → OPENAI_API_KEY → GOOGLE_API_KEY → Ollama.
    Falls back to Ollama if no API key is set and Ollama is reachable.
    Raises CPEError if no backend is available.
    """
    import os
    if os.environ.get("ANTHROPIC_API_KEY"):
        from .anthropic import AnthropicAdapter
        return AnthropicAdapter(model=model or "claude-opus-4-6")
    if os.environ.get("OPENAI_API_KEY"):
        from .openai import OpenAIAdapter
        return OpenAIAdapter(model=model or "gpt-4o")
    if os.environ.get("GOOGLE_API_KEY"):
        from .google import GoogleAdapter
        return GoogleAdapter(model=model or "gemini-2.0-flash")
    from .ollama import OllamaAdapter
    ollama = OllamaAdapter(model=model or "llama3.2")
    if ollama.is_available():
        return ollama
    raise CPEError(
        "No CPE backend available. Set ANTHROPIC_API_KEY, OPENAI_API_KEY, or "
        "GOOGLE_API_KEY, or start Ollama locally (https://ollama.com)."
    )
