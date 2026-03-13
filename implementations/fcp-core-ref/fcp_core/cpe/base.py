"""
CPE Adapter interface.

Defines FCPContext (input to every adapter) and CPEResponse (output),
plus the CPEAdapter Protocol that all adapters implement.

Topology detection is also here — HACA-Core requires TRANSPARENT; adapters
enforce this at construction time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Topology
# ---------------------------------------------------------------------------

class Topology:
    TRANSPARENT = "transparent"
    OPAQUE      = "opaque"


# ---------------------------------------------------------------------------
# Context (input to invoke)  — mirrors Boot Manifest §5.1
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class FCPContext:
    """Neutral representation of everything the CPE needs for one invocation.

    Each adapter formats these fields into the wire format its API expects.
    """
    # §5.1 Boot Manifest sections, in assembly order.
    persona: list[str]          # persona/ file contents, lexicographic order
    boot_protocol: str          # boot.md content
    skills_index: str           # JSON-serialised SkillIndex (CPE-visible subset)
    skill_blocks: list[str]     # one rendered block per authorized skill
    memory: list[str]           # working-memory targets + active_context, priority order
    session: list[dict]         # ACP envelopes from session.jsonl, newest-first
    presession: list[dict]      # ACP envelopes from io/inbox/presession/, arrival order

    # Tool declarations passed to the CPE on every invocation.
    tools: list[dict] = field(default_factory=list)


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

    Implementations must be constructable with (api_key, model, topology).
    topology must be Topology.TRANSPARENT for HACA-Core compliance.
    """

    def invoke(self, context: FCPContext) -> CPEResponse:
        """Send *context* to the CPE and return a normalised response.

        Raises CPEError on network failure, authentication error, or
        any non-retryable API error.  Retry logic lives in the session loop.
        """
        ...  # pragma: no cover


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
