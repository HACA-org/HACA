"""
Pairing adapter — bridges FCP to an external AI agent via the FCP MCP Server.

Architecture
------------
Instead of running its own HTTP server, this adapter communicates through the
filesystem: it writes a prompt to ~/.fcp/pairing/<session-id>.request.json and
waits for the MCP server (fcp_mcp_server.py) to deliver a response to
~/.fcp/pairing/<session-id>.response.json.

The MCP server is a separate, persistent process that any MCP-capable IDE or
CLI (Claude Code, Cursor, Zed, etc.) can connect to. It exposes two tools:
  - fcp_poll    — returns the pending prompt for a session (or empty if none)
  - fcp_respond — writes the completion back, unblocking invoke()

File layout (~/.fcp/pairing/)
------------------------------
  <session-id>.meta.json      — session key, entity_id, started_at
  <session-id>.request.json   — prompt written by invoke(); deleted after poll
  <session-id>.response.json  — completion written by MCP server; deleted after read

Session ID
----------
Generated as a short random hex string (8 chars). Kept in the meta file so the
MCP server can list active sessions and the operator can identify them.

Lifecycle
---------
PairingAdapter creates the meta file on __init__ and removes all session files
on stop(). The MCP server scans the pairing dir for active sessions.
"""

from __future__ import annotations

import json
import os
import secrets
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .base import CPEError, CPEResponse, ToolUseCall

if TYPE_CHECKING:
    from ..store import Layout

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PAIRING_DIR     = Path.home() / ".fcp" / "pairing"
_INVOKE_TIMEOUT  = 300    # seconds — how long invoke() waits for a response
_POLL_INTERVAL   = 0.25   # seconds — how often invoke() checks for response file


# ---------------------------------------------------------------------------
# PairingAdapter
# ---------------------------------------------------------------------------

class PairingAdapter:
    """CPEAdapter that delegates inference to an external agent via the MCP server.

    The external agent connects to fcp_mcp_server via any MCP-capable IDE/CLI,
    polls for prompts with fcp_poll, and posts completions with fcp_respond.
    invoke() writes a .request.json file and blocks until .response.json appears.
    """

    def __init__(self, api_key: str = "", model: str = "external", layout: "Layout | None" = None) -> None:
        self._model      = model
        self._layout     = layout
        self._session_id = secrets.token_hex(4)   # e.g. "a3f1c9b2"
        self._key        = self._gen_key()
        self._pairing_dir = _PAIRING_DIR
        self._pairing_dir.mkdir(parents=True, exist_ok=True)
        self._meta_path     = self._pairing_dir / f"{self._session_id}.meta.json"
        self._request_path  = self._pairing_dir / f"{self._session_id}.request.json"
        self._response_path = self._pairing_dir / f"{self._session_id}.response.json"
        self._write_meta()
        self._print_banner()

    # ------------------------------------------------------------------ lifecycle

    @staticmethod
    def _gen_key() -> str:
        chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        seg = "".join(secrets.choice(chars) for _ in range(4))
        let = secrets.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
        return f"HACA-{seg}-{let}"

    def _write_meta(self) -> None:
        meta = {
            "session_id": self._session_id,
            "key":        self._key,
            "model":      self._model,
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "status":     "active",
        }
        self._meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    def _print_banner(self) -> None:
        sep = "─" * 52
        print(f"\n{sep}")
        print("  PAIRING MODE ACTIVE")
        print(f"  Session  : {self._session_id}")
        print(f"  Key      : {self._key}")
        print(f"  MCP Dir  : {self._pairing_dir}")
        print("  Connect the FCP MCP Server to your IDE/CLI.")
        print(f"{sep}\n", flush=True)

    def stop(self) -> None:
        """Remove all session files for this pairing session."""
        for path in (self._meta_path, self._request_path, self._response_path):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass

    def __del__(self) -> None:
        try:
            self.stop()
        except Exception:
            pass

    # ------------------------------------------------------------------ invoke

    def invoke(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> CPEResponse:
        """Write prompt to request file and block until response file appears."""
        # Remove stale response from previous turn
        self._response_path.unlink(missing_ok=True)

        prompt: dict[str, Any] = {
            "session_id": self._session_id,
            "system":     system,
            "messages":   messages,
            "tools":      tools,
        }
        self._request_path.write_text(
            json.dumps(prompt, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # Fire on_prompt_pending hook to notify external systems (e.g., MCP server)
        if self._layout:
            from ..hooks import run_hook
            run_hook(
                self._layout,
                "on_prompt_pending",
                {
                    "session_id": self._session_id,
                    "request_file": str(self._request_path),
                },
            )

        # Wait for the MCP server to deliver a response
        deadline = time.monotonic() + _INVOKE_TIMEOUT
        while time.monotonic() < deadline:
            if self._response_path.exists():
                try:
                    data = json.loads(self._response_path.read_text(encoding="utf-8"))
                    self._response_path.unlink(missing_ok=True)
                    return _parse_response(data)
                except (json.JSONDecodeError, OSError):
                    pass  # file still being written — retry next tick
            time.sleep(_POLL_INTERVAL)

        # Timeout — clean up request file so MCP server doesn't deliver stale prompt
        self._request_path.unlink(missing_ok=True)
        raise CPEError(
            f"Pairing: no response received within {_INVOKE_TIMEOUT}s. "
            "Is the FCP MCP Server running and an agent connected?"
        )

    # ------------------------------------------------------------------ status

    def is_available(self) -> bool:
        return self._meta_path.exists()


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

def _parse_response(data: dict[str, Any]) -> CPEResponse:
    """Parse the completion payload written by the external agent.

    Expected shape (all fields optional except at least one of text/tool_use_calls):
    {
        "text": "...",
        "tool_use_calls": [{"id": "...", "tool": "...", "input": {...}}],
        "input_tokens":  0,
        "output_tokens": 0,
        "stop_reason":   "end_turn"
    }
    """
    text    = data.get("text") or ""
    stop    = data.get("stop_reason") or "end_turn"
    in_tok  = int(data.get("input_tokens",  0))
    out_tok = int(data.get("output_tokens", 0))

    tool_calls: list[ToolUseCall] = []
    for tc in data.get("tool_use_calls", []):
        tool_calls.append(ToolUseCall(
            id=tc.get("id", ""),
            tool=tc.get("tool", ""),
            input=tc.get("input", {}),
        ))

    return CPEResponse(
        text=text,
        tool_use_calls=tool_calls,
        input_tokens=in_tok,
        output_tokens=out_tok,
        stop_reason=stop,
    )
