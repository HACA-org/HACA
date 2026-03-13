"""CPE backend — FCP-Core §3.2 (cpe.topology / cpe.backend).

Um único módulo, um único HTTPBackend.  Cada provider é apenas um conjunto
de funções puras que transformam o contexto num request HTTP e a resposta
num string — sem classes duplicadas.

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
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class CPEError(Exception):
    """Raised when a CPE invocation fails."""


# ---------------------------------------------------------------------------
# Provider configuration table
#
# Each entry is a dict with three callables:
#   url(model, api_key)           → str
#   headers(api_key)              → dict
#   build_body(model, msgs, sys)  → dict   (msgs = list of {role, content})
#   parse(response_dict)          → str
# ---------------------------------------------------------------------------

def _ollama_url(model: str, _key: str) -> str:
    return "http://localhost:11434/api/chat"

def _ollama_headers(_key: str) -> dict[str, str]:
    return {"Content-Type": "application/json"}

def _ollama_build(model: str, messages: list[dict], system: str) -> dict:
    msgs = ([{"role": "system", "content": system}] if system else []) + messages
    return {"model": model, "messages": msgs, "stream": False, "num_ctx": 32768}

def _ollama_parse(resp: dict) -> str:
    return resp["message"]["content"]


def _anthropic_url(_model: str, _key: str) -> str:
    return "https://api.anthropic.com/v1/messages"

def _anthropic_headers(key: str) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
    }

def _anthropic_build(model: str, messages: list[dict], system: str) -> dict:
    body: dict[str, Any] = {"model": model, "max_tokens": 8192, "messages": messages}
    if system:
        body["system"] = system
    return body

def _anthropic_parse(resp: dict) -> str:
    return resp["content"][0]["text"]


def _openai_url(_model: str, _key: str) -> str:
    return "https://api.openai.com/v1/chat/completions"

def _openai_headers(key: str) -> dict[str, str]:
    return {"Content-Type": "application/json", "Authorization": f"Bearer {key}"}

def _openai_build(model: str, messages: list[dict], system: str) -> dict:
    msgs = ([{"role": "system", "content": system}] if system else []) + messages
    return {"model": model, "messages": msgs, "max_tokens": 8192}

def _openai_parse(resp: dict) -> str:
    return resp["choices"][0]["message"]["content"]


def _google_url(model: str, key: str) -> str:
    base = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    return f"{base}?key={urllib.parse.quote(key, safe='')}"

def _google_headers(_key: str) -> dict[str, str]:
    return {"Content-Type": "application/json"}

def _google_build(_model: str, messages: list[dict], system: str) -> dict:
    contents = [{"role": m["role"], "parts": [{"text": m["content"]}]} for m in messages]
    body: dict[str, Any] = {"contents": contents}
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    return body

def _google_parse(resp: dict) -> str:
    parts = resp["candidates"][0]["content"]["parts"]
    return "".join(p.get("text", "") for p in parts)


_PROVIDERS: dict[str, dict] = {
    "ollama":    {"url": _ollama_url,    "headers": _ollama_headers,    "build": _ollama_build,    "parse": _ollama_parse},
    "anthropic": {"url": _anthropic_url, "headers": _anthropic_headers, "build": _anthropic_build, "parse": _anthropic_parse},
    "openai":    {"url": _openai_url,    "headers": _openai_headers,    "build": _openai_build,    "parse": _openai_parse},
    "google":    {"url": _google_url,    "headers": _google_headers,    "build": _google_build,    "parse": _google_parse},
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

    def invoke(self, system: str, messages: list[dict]) -> str:
        """Send a turn to the CPE and return the raw response text.

        Args:
            system:   System prompt (Boot Manifest — persona, boot protocol,
                      skills index, memory).  Stays fixed throughout the session.
            messages: Chat history as alternating user/assistant dicts.
                      The last entry is always the current user turn.

        Returns:
            Raw CPE response string (may contain component blocks).

        Raises:
            CPEError: on any HTTP or parsing failure.
        """
        cfg  = _PROVIDERS[self.provider]
        body = cfg["build"](self.model, messages, system)
        url      = cfg["url"](self.model, self.api_key)
        headers  = cfg["headers"](self.api_key)

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
            return cfg["parse"](resp_data)
        except (KeyError, IndexError, TypeError) as exc:
            raise CPEError(
                f"{self.provider} unexpected response format: {resp_data!r}"
            ) from exc


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
