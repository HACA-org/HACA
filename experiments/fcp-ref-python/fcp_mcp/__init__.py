#!/usr/bin/env python3
"""
FCP MCP Server — bridges any MCP-capable IDE/CLI to an active FCP pairing session.

Usage
-----
Add this server to your MCP configuration (e.g. Claude Code, Cursor, Zed):

  {
    "mcpServers": {
      "fcp": {
        "command": "python3",
        "args": ["/path/to/fcp_mcp_server.py"]
      }
    }
  }

Or run directly for testing:
  python3 fcp_mcp_server.py

Tools exposed
-------------
fcp_sessions  — list all active pairing sessions in ~/.fcp/pairing/
fcp_poll      — return the pending prompt for a session (empty if none pending)
fcp_respond   — deliver a completion back to the waiting FCP invoke()

Protocol
--------
The FCP PairingAdapter writes prompts to:
  ~/.fcp/pairing/<session-id>.request.json

This server reads that file (fcp_poll) and writes completions to:
  ~/.fcp/pairing/<session-id>.response.json

PairingAdapter polls for the response file and unblocks as soon as it appears.

Dependencies
------------
mcp — install with: pip install mcp
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    print(
        "ERROR: 'mcp' package not found.\n"
        "Install it with: pip install mcp",
        file=sys.stderr,
    )
    sys.exit(1)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PAIRING_DIR = Path.home() / ".fcp" / "pairing"

# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "FCP Pairing",
    instructions=(
        "You are connected to an active FCP (Filesystem Cognitive Platform) session. "
        "Use fcp_sessions to see active sessions, fcp_poll to retrieve the pending prompt, "
        "and fcp_respond to deliver your completion back to the FCP entity. "
        "Keep polling until fcp_poll returns a prompt, then respond immediately."
    ),
)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def fcp_sessions() -> str:
    """List all active FCP pairing sessions.

    Returns a JSON array of active sessions with their session_id, key, and
    started_at. Use the session_id with fcp_poll and fcp_respond.
    """
    _PAIRING_DIR.mkdir(parents=True, exist_ok=True)
    sessions = []
    for meta_file in sorted(_PAIRING_DIR.glob("*.meta.json")):
        try:
            data = json.loads(meta_file.read_text(encoding="utf-8"))
            sessions.append({
                "session_id": data.get("session_id", meta_file.stem.replace(".meta", "")),
                "key":        data.get("key", ""),
                "model":      data.get("model", ""),
                "started_at": data.get("started_at", ""),
                "status":     data.get("status", "unknown"),
                "pending":    (_PAIRING_DIR / f"{data.get('session_id', '')}.request.json").exists(),
            })
        except (json.JSONDecodeError, OSError):
            continue
    if not sessions:
        return json.dumps({"sessions": [], "message": "No active pairing sessions found. Start FCP with backend=pairing first."})
    return json.dumps({"sessions": sessions}, indent=2)


@mcp.tool()
def fcp_poll(session_id: str) -> str:
    """Retrieve the pending prompt from an active FCP session.

    Call this in a loop until a prompt is returned. When the FCP entity needs
    inference, it writes a prompt file that this tool reads and removes.

    Args:
        session_id: The session ID from fcp_sessions.

    Returns:
        JSON with the prompt (system, messages, tools) if pending,
        or {"pending": false} if no prompt is ready yet.
    """
    request_path = _PAIRING_DIR / f"{session_id}.request.json"
    if not request_path.exists():
        return json.dumps({"pending": False})
    try:
        data = json.loads(request_path.read_text(encoding="utf-8"))
        request_path.unlink(missing_ok=True)
        data["pending"] = True
        return json.dumps(data, ensure_ascii=False)
    except (json.JSONDecodeError, OSError) as exc:
        return json.dumps({"pending": False, "error": str(exc)})


@mcp.tool()
def fcp_respond(
    session_id: str,
    text: str,
    tool_use_calls: list[dict[str, Any]] | None = None,
    stop_reason: str = "end_turn",
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> str:
    """Deliver a completion back to the waiting FCP session.

    Call this after processing the prompt from fcp_poll. The FCP entity is
    blocking in invoke() waiting for this response.

    Args:
        session_id:     The session ID from fcp_sessions.
        text:           The narrative text response (may be empty if tool_use_calls present).
        tool_use_calls: Optional list of tool calls: [{"id": "...", "tool": "...", "input": {...}}]
        stop_reason:    "end_turn" | "tool_use" | "max_tokens"
        input_tokens:   Token count (informational only).
        output_tokens:  Token count (informational only).

    Returns:
        {"status": "delivered"} on success, or an error message.
    """
    meta_path = _PAIRING_DIR / f"{session_id}.meta.json"
    if not meta_path.exists():
        return json.dumps({"status": "error", "message": f"Session {session_id!r} not found."})

    response: dict[str, Any] = {
        "text":           text,
        "tool_use_calls": tool_use_calls or [],
        "stop_reason":    stop_reason,
        "input_tokens":   input_tokens,
        "output_tokens":  output_tokens,
        "delivered_at":   time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    response_path = _PAIRING_DIR / f"{session_id}.response.json"
    try:
        response_path.write_text(
            json.dumps(response, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return json.dumps({"status": "delivered", "session_id": session_id})
    except OSError as exc:
        return json.dumps({"status": "error", "message": str(exc)})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
