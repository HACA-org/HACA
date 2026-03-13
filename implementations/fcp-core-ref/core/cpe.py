"""CPE backend — FCP-Core §3.2 (cpe.topology / cpe.backend).

Um único módulo, um único HTTPBackend.  Cada provider é apenas um conjunto
de funções puras que transformam o contexto num request HTTP e a resposta
num CPEResponse — sem classes duplicadas.

Formato do campo `cpe.backend` em state/baseline.json:
  "ollama"                         → Ollama, auto-selecciona modelo
  "ollama:llama3.2"                → Ollama, modelo específico
  "anthropic:claude-3-5-sonnet-20241022"
  "openai:gpt-4o"
  "google:gemini-2.0-flash"

Auto-detecção (usada no FAP quando o backend ainda não foi configurado):
  1. Ollama a correr em localhost:11434 → usa primeiro modelo disponível
  2. ANTHROPIC_API_KEY presente        → anthropic:claude-3-5-sonnet-20241022
  3. OPENAI_API_KEY presente           → openai:gpt-4o
  4. GOOGLE_API_KEY presente           → google:gemini-2.0-flash
  5. RuntimeError — nenhum backend disponível
"""

from __future__ import annotations

import json
import os
import uuid
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class CPEError(Exception):
    """Raised when a CPE invocation fails."""


# ---------------------------------------------------------------------------
# Response + ToolResult types
# ---------------------------------------------------------------------------

@dataclass
class ToolResult:
    """Result of a single tool call dispatched by the session loop."""
    tool_call_id: str
    content: str
    is_error: bool = False


@dataclass
class CPEResponse:
    """Parsed response from one CPE invocation.

    text:        Narrative text (may be empty if only tool calls were emitted).
    tool_calls:  List of tool invocations; each dict has keys id, name, input.
    raw_content: Full content list from the API (needed to replay in chat history).
    """
    text: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    raw_content: list[dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# FCP tool definitions — passed to every CPE invocation
# ---------------------------------------------------------------------------

FCP_TOOLS: list[dict[str, Any]] = [
    {
        "name": "fcp_mil",
        "description": (
            "Memory and lifecycle actions. "
            "memory_write: persist a note or observation. "
            "memory_recall: search previously saved notes by keyword. "
            "closure_payload: session-close consolidation (summary + handoff)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": ["memory_write", "memory_recall", "closure_payload"],
                    "description": "Action type.",
                },
                "content": {
                    "type": "string",
                    "description": "Text to save (memory_write).",
                },
                "query": {
                    "type": "string",
                    "description": "Search query (memory_recall).",
                },
                "consolidation": {
                    "type": "string",
                    "description": "Semantic summary of this session (closure_payload).",
                },
                "working_memory": {
                    "type": "array",
                    "description": "Memory artefact paths to carry forward (closure_payload).",
                    "items": {"type": "object"},
                },
                "session_handoff": {
                    "type": "object",
                    "description": "Pending tasks and next steps for the next session (closure_payload).",
                },
            },
            "required": ["type"],
        },
    },
    {
        "name": "fcp_exec",
        "description": (
            "Skill execution. "
            "skill_request: invoke a skill listed in [SKILLS INDEX]. "
            "skill_info: read the full documentation for a skill."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": ["skill_request", "skill_info"],
                    "description": "Action type.",
                },
                "skill": {
                    "type": "string",
                    "description": "Skill name exactly as listed in [SKILLS INDEX].",
                },
                "params": {
                    "type": "object",
                    "description": "Skill parameters (skill_request only).",
                },
            },
            "required": ["type", "skill"],
        },
    },
    {
        "name": "fcp_sil",
        "description": (
            "Structural integrity actions. "
            "evolution_proposal: propose a change to persona, config, or skills. "
            "session_close: end the session safely (always emit closure_payload first)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": ["evolution_proposal", "session_close"],
                    "description": "Action type.",
                },
                "content": {
                    "type": "string",
                    "description": "Human-readable description of the proposed change (evolution_proposal).",
                },
                "target_file": {
                    "type": "string",
                    "description": (
                        "Target path for Endure, e.g. workspace/stage/<skill_name> "
                        "(evolution_proposal)."
                    ),
                },
            },
            "required": ["type"],
        },
    },
]


# ---------------------------------------------------------------------------
# Provider helpers — build / parse_response
# ---------------------------------------------------------------------------

# ── Anthropic ──────────────────────────────────────────────────────────────

def _anthropic_url(_model: str, _key: str) -> str:
    return "https://api.anthropic.com/v1/messages"

def _anthropic_headers(key: str) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
    }

def _anthropic_build(
    model: str,
    messages: list[dict],
    system: str,
    tools: list[dict] | None = None,
) -> dict:
    body: dict[str, Any] = {"model": model, "max_tokens": 8192, "messages": messages}
    if system:
        body["system"] = system
    if tools:
        body["tools"] = tools
    return body

def _anthropic_parse_response(resp: dict) -> CPEResponse:
    text_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    content: list[dict[str, Any]] = resp.get("content", [])
    for block in content:
        btype = block.get("type", "")
        if btype == "text":
            text_parts.append(block.get("text", ""))
        elif btype == "tool_use":
            tool_calls.append({
                "id":    block["id"],
                "name":  block["name"],
                "input": block.get("input", {}),
            })
    return CPEResponse(
        text=" ".join(text_parts).strip(),
        tool_calls=tool_calls,
        raw_content=content,
    )

def _anthropic_make_tool_results(results: list[ToolResult]) -> list[dict]:
    """Return one user message containing all tool_result blocks (Anthropic format)."""
    blocks = [
        {
            "type":        "tool_result",
            "tool_use_id": r.tool_call_id,
            "content":     r.content,
            **({"is_error": True} if r.is_error else {}),
        }
        for r in results
    ]
    return [{"role": "user", "content": blocks}]


# ── OpenAI / Ollama ────────────────────────────────────────────────────────

def _openai_url(_model: str, _key: str) -> str:
    return "https://api.openai.com/v1/chat/completions"

def _openai_headers(key: str) -> dict[str, str]:
    return {"Content-Type": "application/json", "Authorization": f"Bearer {key}"}

def _ollama_url(_model: str, _key: str) -> str:
    return "http://localhost:11434/api/chat"

def _ollama_headers(_key: str) -> dict[str, str]:
    return {"Content-Type": "application/json"}

def _openai_build(
    model: str,
    messages: list[dict],
    system: str,
    tools: list[dict] | None = None,
) -> dict:
    msgs = ([{"role": "system", "content": system}] if system else []) + messages
    body: dict[str, Any] = {"model": model, "messages": msgs, "max_tokens": 8192}
    if tools:
        body["tools"] = _fcp_tools_to_openai(tools)
    return body

def _ollama_normalize_messages(messages: list[dict]) -> list[dict]:
    """Normalize chat history for Ollama native API.

    Ollama requires content to be a string.  When the session loop appends
    an assistant message with array raw_content (containing text + tool_use
    blocks), this converts it back to Ollama's native format:
      {"role": "assistant", "content": "<text>", "tool_calls": [{...}]}
    """
    result = []
    for msg in messages:
        content = msg.get("content")
        if not isinstance(content, list):
            result.append(msg)
            continue
        text_parts: list[str] = []
        tool_calls: list[dict] = []
        for block in content:
            if block.get("type") == "text":
                text_parts.append(block.get("text", ""))
            elif block.get("type") == "tool_use":
                tool_calls.append({
                    "function": {
                        "name":      block["name"],
                        "arguments": block.get("input", {}),
                    }
                })
        normalized: dict[str, Any] = dict(msg)
        normalized["content"] = "".join(text_parts)
        if tool_calls:
            normalized["tool_calls"] = tool_calls
        result.append(normalized)
    return result

def _ollama_build(
    model: str,
    messages: list[dict],
    system: str,
    tools: list[dict] | None = None,
) -> dict:
    msgs = (
        ([{"role": "system", "content": system}] if system else [])
        + _ollama_normalize_messages(messages)
    )
    body: dict[str, Any] = {"model": model, "messages": msgs, "stream": False, "num_ctx": 32768}
    if tools:
        body["tools"] = _fcp_tools_to_openai(tools)
    return body

def _ollama_parse_response(resp: dict) -> CPEResponse:
    """Parse native Ollama /api/chat response (different layout from OpenAI)."""
    msg = resp["message"]
    text = msg.get("content") or ""
    tool_calls: list[dict[str, Any]] = []
    raw_content: list[dict[str, Any]] = []
    if text:
        raw_content.append({"type": "text", "text": text})
    for tc in msg.get("tool_calls") or []:
        fn   = tc["function"]
        args = fn.get("arguments") or {}
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except Exception:
                args = {}
        call_id = str(uuid.uuid4())
        tool_calls.append({"id": call_id, "name": fn["name"], "input": args})
        raw_content.append({"type": "tool_use", "id": call_id, "name": fn["name"], "input": args})
    return CPEResponse(text=text.strip(), tool_calls=tool_calls, raw_content=raw_content)

def _ollama_make_tool_results(results: list[ToolResult]) -> list[dict]:
    """Ollama native /api/chat does not use tool_call_id in tool results."""
    return [{"role": "tool", "content": r.content} for r in results]

def _openai_parse_response(resp: dict) -> CPEResponse:
    msg = resp["choices"][0]["message"]
    text = msg.get("content") or ""
    tool_calls: list[dict[str, Any]] = []
    raw_content: list[dict[str, Any]] = []
    if text:
        raw_content.append({"type": "text", "text": text})
    for tc in msg.get("tool_calls") or []:
        try:
            inp = json.loads(tc["function"]["arguments"])
        except Exception:
            inp = {}
        tool_calls.append({
            "id":    tc["id"],
            "name":  tc["function"]["name"],
            "input": inp,
        })
        raw_content.append({
            "type":  "tool_use",
            "id":    tc["id"],
            "name":  tc["function"]["name"],
            "input": inp,
        })
    return CPEResponse(text=text.strip(), tool_calls=tool_calls, raw_content=raw_content)

def _openai_make_tool_results(results: list[ToolResult]) -> list[dict]:
    """Return one message per tool result (OpenAI format)."""
    return [
        {
            "role":         "tool",
            "tool_call_id": r.tool_call_id,
            "content":      r.content,
        }
        for r in results
    ]

def _fcp_tools_to_openai(tools: list[dict]) -> list[dict]:
    """Convert Anthropic-style tool defs to OpenAI function-calling format."""
    return [
        {
            "type": "function",
            "function": {
                "name":        t["name"],
                "description": t.get("description", ""),
                "parameters":  t.get("input_schema", {}),
            },
        }
        for t in tools
    ]


# ── Google ─────────────────────────────────────────────────────────────────

def _google_url(model: str, key: str) -> str:
    base = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    return f"{base}?key={urllib.parse.quote(key, safe='')}"

def _google_headers(_key: str) -> dict[str, str]:
    return {"Content-Type": "application/json"}

def _google_build(
    _model: str,
    messages: list[dict],
    system: str,
    tools: list[dict] | None = None,
) -> dict:
    if tools:
        raise CPEError("Google provider does not support FCP tool_use yet.")
    contents = [{"role": m["role"], "parts": [{"text": m["content"]}]} for m in messages]
    body: dict[str, Any] = {"contents": contents}
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    return body

def _google_parse_response(resp: dict) -> CPEResponse:
    parts = resp["candidates"][0]["content"]["parts"]
    text = "".join(p.get("text", "") for p in parts)
    content = [{"type": "text", "text": text}]
    return CPEResponse(text=text.strip(), tool_calls=[], raw_content=content)

def _google_make_tool_results(_results: list[ToolResult]) -> list[dict]:
    raise CPEError("Google provider does not support FCP tool_use yet.")


# ---------------------------------------------------------------------------
# Provider configuration table
# ---------------------------------------------------------------------------

_PROVIDERS: dict[str, dict] = {
    "ollama": {
        "url":              _ollama_url,
        "headers":          _ollama_headers,
        "build":            _ollama_build,
        "parse_response":   _ollama_parse_response,
        "make_tool_results": _ollama_make_tool_results,
    },
    "anthropic": {
        "url":              _anthropic_url,
        "headers":          _anthropic_headers,
        "build":            _anthropic_build,
        "parse_response":   _anthropic_parse_response,
        "make_tool_results": _anthropic_make_tool_results,
    },
    "openai": {
        "url":              _openai_url,
        "headers":          _openai_headers,
        "build":            _openai_build,
        "parse_response":   _openai_parse_response,
        "make_tool_results": _openai_make_tool_results,
    },
    "google": {
        "url":              _google_url,
        "headers":          _google_headers,
        "build":            _google_build,
        "parse_response":   _google_parse_response,
        "make_tool_results": _google_make_tool_results,
    },
}

DEFAULT_MODELS = {
    "anthropic": "claude-3-5-sonnet-20241022",
    "openai":    "gpt-4o",
    "google":    "gemini-2.0-flash",
}


# ---------------------------------------------------------------------------
# CPEBackend
# ---------------------------------------------------------------------------

class CPEBackend:
    """HTTP CPE backend configurável por provider + modelo.

    Args:
        backend_spec: string no formato "provider:model" ou "provider".
        api_key:      chave de API (se None, lida da env var correspondente).
        timeout:      timeout HTTP em segundos.
    """

    def __init__(
        self,
        backend_spec: str,
        api_key:      str | None = None,
        timeout:      int = 300,
    ) -> None:
        provider, _, model = backend_spec.partition(":")
        self.provider = provider.strip().lower()
        self.model    = model.strip() or DEFAULT_MODELS.get(self.provider, "")
        self.timeout  = timeout

        if self.provider not in _PROVIDERS:
            raise ValueError(
                f"Unknown CPE provider {self.provider!r}.  "
                f"Available: {list(_PROVIDERS)}"
            )

        # Resolve API key
        if api_key is not None:
            self.api_key = api_key
        else:
            env_map = {
                "anthropic": "ANTHROPIC_API_KEY",
                "openai":    "OPENAI_API_KEY",
                "google":    "GOOGLE_API_KEY",
                "ollama":    "",
            }
            self.api_key = os.environ.get(env_map.get(self.provider, ""), "")

    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return f"{self.provider}:{self.model}" if self.model else self.provider

    def invoke(
        self,
        system:   str,
        messages: list[dict],
        tools:    list[dict] | None = None,
    ) -> CPEResponse:
        """Send a turn to the CPE and return a structured CPEResponse.

        Args:
            system:   System prompt (Boot Manifest — persona, boot protocol,
                      skills index, memory).  Stays fixed throughout the session.
            messages: Chat history as alternating user/assistant turns.
                      Content may be a string (text-only turns) or a list
                      of content blocks (turns with tool_use / tool_results).
            tools:    Tool definitions to pass to the model.  Defaults to None
                      (no tools — text-only response).

        Returns:
            CPEResponse with text, tool_calls, and raw_content.

        Raises:
            CPEError: on any HTTP, parsing, or unsupported-feature failure.
        """
        cfg  = _PROVIDERS[self.provider]
        body = cfg["build"](self.model, messages, system, tools)
        url     = cfg["url"](self.model, self.api_key)
        headers = cfg["headers"](self.api_key)

        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body_err = exc.read().decode("utf-8", errors="replace")
            raise CPEError(f"{self.provider} HTTP {exc.code}: {body_err}") from exc
        except urllib.error.URLError as exc:
            raise CPEError(f"{self.provider} unreachable: {exc}") from exc
        except Exception as exc:
            raise CPEError(f"{self.provider} invocation failed: {exc}") from exc

        try:
            return cfg["parse_response"](resp_data)
        except (KeyError, IndexError, TypeError) as exc:
            raise CPEError(
                f"{self.provider} unexpected response format: {resp_data!r}"
            ) from exc

    def make_tool_result_message(self, results: list[ToolResult]) -> list[dict]:
        """Convert tool results to provider-specific chat history entries.

        Returns a list of message dicts to extend into chat_history:
          - Anthropic: one user message with tool_result content blocks.
          - OpenAI/Ollama: one tool message per result.
        """
        return _PROVIDERS[self.provider]["make_tool_results"](results)


# ---------------------------------------------------------------------------
# Auto-detecção de backend (usada no FAP)
# ---------------------------------------------------------------------------

def detect_backend() -> str:
    """Detecta e retorna o backend spec disponível no ambiente actual.

    Ordem de preferência:
      1. Ollama (probe localhost:11434)
      2. ANTHROPIC_API_KEY
      3. OPENAI_API_KEY
      4. GOOGLE_API_KEY

    Returns:
        Backend spec string (ex: "ollama:llama3.2", "anthropic:claude-3-5-sonnet-20241022").

    Raises:
        RuntimeError: se nenhum backend estiver disponível.
    """
    # 1. Ollama
    try:
        with urllib.request.urlopen(
            "http://localhost:11434/api/tags", timeout=3
        ) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = data.get("models", [])
            if models:
                return f"ollama:{models[0]['name']}"
            return "ollama"
    except Exception:
        pass

    # 2-4. Cloud providers via env
    for provider, env_var in [
        ("anthropic", "ANTHROPIC_API_KEY"),
        ("openai",    "OPENAI_API_KEY"),
        ("google",    "GOOGLE_API_KEY"),
    ]:
        if os.environ.get(env_var, "").strip():
            return f"{provider}:{DEFAULT_MODELS[provider]}"

    raise RuntimeError(
        "No CPE backend available.  Start Ollama or set one of: "
        "ANTHROPIC_API_KEY, OPENAI_API_KEY, GOOGLE_API_KEY."
    )
