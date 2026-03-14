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

    Intended layout for all adapters:
      system          — persona only (identity, values, constraints)
      messages[0]     — boot_protocol + skills (instruction block, role: user)
      messages[1..n]  — reconstructed conversation history (role: user / assistant)

    This structure ensures instruction and history are never mixed, which
    matters for weaker models that conflate repeated instructions with new stimuli.
    """
    # §5.1 Boot Manifest sections, in assembly order.
    persona: list[str]          # persona/ file contents, lexicographic order
    boot_protocol: str          # boot.md content — already prefixed with HACA version header
    skills_index: str           # JSON-serialised SkillIndex (CPE-visible subset)
    skill_blocks: list[str]     # one rendered block per authorized skill
    memory: list[str]           # working-memory targets + active_context, priority order
    session: list[dict]         # ACP envelopes from session.jsonl, oldest-first
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
# Shared context formatting helpers (used by all adapters)
# ---------------------------------------------------------------------------

def build_system(ctx: FCPContext) -> str:
    """Persona only — identity, values, constraints.

    This is the stable identity layer. It never contains operational
    instructions so the model does not re-interpret identity text as commands.
    """
    return "\n\n".join(ctx.persona) if ctx.persona else "You are a helpful assistant."


def build_instruction_block(ctx: FCPContext) -> str:
    """Boot protocol + skills — the single instruction block sent once.

    Placed as messages[0] (role: user) so the model receives it as a clear,
    one-time directive before any conversation history.
    Memory is included here so it is read before the session turns.
    """
    parts: list[str] = [ctx.boot_protocol]
    if ctx.memory:
        parts.append("## Active Memory\n\n" + "\n\n---\n\n".join(ctx.memory))
    if ctx.skills_index and ctx.skills_index.strip() not in ("", '{"skills": []}'):
        parts.append("## Available Skills\n\n" + ctx.skills_index)
        for block in ctx.skill_blocks:
            parts.append(block)
    return "\n\n".join(parts)


def build_history(ctx: FCPContext) -> list[tuple[str, str]]:
    """Reconstruct conversation history as (role, text) pairs from session records.

    ACP envelopes are interpreted by actor:
      operator / user  → role "user"
      cpe / assistant  → role "assistant"
      fcp / sil / mil  → role "user"  (system stimuli, surface as context)
    Tool results are formatted as readable text under the assistant turn.

    Returns oldest-first list of (role, text) — adapters convert to wire format.
    Consecutive same-role entries are merged to avoid invalid alternation.
    """
    pairs: list[tuple[str, str]] = []

    for env in ctx.session:
        actor = str(env.get("actor", env.get("source", "")))
        raw_data = env.get("data", "")

        # parse data field (may be JSON string or plain text)
        if isinstance(raw_data, str):
            try:
                import json as _json
                data = _json.loads(raw_data)
            except Exception:
                data = raw_data
        else:
            data = raw_data

        # determine role
        if actor in ("operator", "user"):
            role = "user"
        elif actor in ("cpe", "assistant"):
            role = "assistant"
        else:
            role = "user"  # system stimuli surface as user context

        # extract text
        if isinstance(data, str):
            text = data.strip()
        elif isinstance(data, dict):
            if "tool_result" in data:
                tr = data["tool_result"]
                text = f"[tool result: {tr.get('tool', '?')}]\n{tr.get('content', '')}"
            else:
                import json as _json
                text = _json.dumps(data, ensure_ascii=False)
        else:
            import json as _json
            text = _json.dumps(data, ensure_ascii=False)

        if not text:
            continue

        # merge consecutive same-role entries
        if pairs and pairs[-1][0] == role:
            prev_role, prev_text = pairs[-1]
            pairs[-1] = (prev_role, prev_text + "\n\n" + text)
        else:
            pairs.append((role, text))

    # presession entries are prepended as user context before history
    if ctx.presession:
        import json as _json
        pre_lines = [_json.dumps(e, ensure_ascii=False) for e in ctx.presession]
        pre_text = "[Pre-session context]\n" + "\n".join(pre_lines)
        if pairs and pairs[0][0] == "user":
            pairs[0] = ("user", pre_text + "\n\n" + pairs[0][1])
        else:
            pairs.insert(0, ("user", pre_text))

    return pairs


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
