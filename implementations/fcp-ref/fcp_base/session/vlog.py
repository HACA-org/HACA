"""
Session verbose logging helpers.
"""

from __future__ import annotations

import json
from typing import Any, TYPE_CHECKING

from ..operator import is_verbose as _is_verbose, get_debugger as _get_debugger
from .. import ui

if TYPE_CHECKING:
    from ..cpe.base import CPEResponse

# Pure display helpers live in ui — import aliases for local use
_DIM   = ui.DIM
_RESET = ui.RESET
_GRAY  = ui.GRAY
_vprint       = ui.vprint
_format_bytes = ui.format_bytes
_compact_json = ui.compact_json


def _vlog(actor: str, msg: str) -> None:
    if not _is_verbose():
        return
    _vprint(f"[{actor}] {msg}")


def _vlog_json(label: str, data: Any) -> None:
    if not _is_verbose():
        return
    _vprint(f"[{label}]")
    _vprint(json.dumps(data, indent=2, ensure_ascii=False))


def _vlog_request(
    system: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    cycle: int,
) -> None:
    """Log cycle header (before CPE invoke)."""
    dbg = _get_debugger()
    if not _is_verbose() and dbg is None:
        return

    if _is_verbose():
        sys_size = _format_bytes(len(system))
        _vprint(f"[CYCLE {cycle}] [→ CPE] {sys_size} system + {len(messages)} msgs + {len(tools)} tools")
        return

    # debugger mode — keep original detailed format
    _vprint("[debugger] fcp→cpe request")
    if dbg in ("boot", "all"):
        _vprint(f"  [system] {len(system)} chars:")
        for line in system.splitlines():
            _vprint(f"    {line}")
        _vprint(f"  [0] user (instruction block) {len(str(messages[0].get('content', '')))} chars:")
        for line in str(messages[0].get("content", "")).splitlines():
            _vprint(f"    {line}")
        _vprint(f"  [1] assistant: {messages[1].get('content', '')}")

    if dbg in ("chat", "all"):
        _vprint(f"  history ({len(messages) - 2} turns):")
        for i, msg in enumerate(messages):
            if i < 2:
                continue
            content = str(msg.get("content", ""))
            _vprint(f"    [{i}] {msg['role']}: {content}")

    _vprint(f"  tools: {[t['name'] for t in tools]}")


def _vlog_cycle_summary(
    response: "CPEResponse",
    elapsed_secs: float,
    tool_log_lines: list[dict[str, Any]],
    ctx_window: int = 0,
) -> None:
    """Print cycle summary: [DISPATCH] tree + [← CPE] line (always visible).

    Tree is always shown. With verbose: includes input/output JSON payloads.
    Without verbose: compact format with sizes and timing only.

    tool_log_lines: list of dicts with tool, input, output, input_size, result_size, status, timing_ms, is_last
    """
    dbg = _get_debugger()
    verbose = _is_verbose()

    # Dispatch block — ALWAYS show (if tools were called)
    if tool_log_lines:
        for tool_info in tool_log_lines:
            tool = tool_info["tool"]
            is_last = tool_info["is_last"]
            input_size = tool_info["input_size"]
            result_size = tool_info["result_size"]
            status = tool_info["status"]
            timing_ms = tool_info["timing_ms"]
            timing_str = f", {timing_ms:.0f}ms" if timing_ms > 10 else ""

            prefix = "  └─" if is_last else "  ├─"

            if verbose:
                print(f"{_DIM}{prefix} {tool}{_RESET}")
                input_json = _compact_json(tool_info["input"])
                output_json = _compact_json(tool_info["output"])
                print(f"{_DIM}{prefix[:-2]}  ├─ input: {input_json}{_RESET}")
                print(f"{_DIM}{prefix[:-2]}  └─ output: {output_json}{_RESET}")
            else:
                print(f"{_DIM}{prefix} {tool}  {input_size} → {status} ({result_size}{timing_str}){_RESET}")

    # CPE response line — ALWAYS show
    _tokens = f"{response.input_tokens:,} ↑ / {response.output_tokens:,} ↓"
    if ctx_window:
        _pct = round(response.input_tokens / ctx_window * 100, 1)
        _tokens += f" | ctx: {_pct}%"
    print(f"{_DIM}  └─ CPE  ⏱ {elapsed_secs:.1f}s | {_tokens} | {response.stop_reason}{_RESET}")
    if verbose and response.text:
        preview = response.text[:50].replace("\n", " ")
        print(f"{_DIM}     └─ text: {preview!r} ({len(response.text)} chars){_RESET}")

    print()

    # Debugger mode
    if dbg and not verbose:
        print(f"{_DIM}[cpe→fcp] response{_RESET}")
        print(f"{_DIM}  stop_reason  : {response.stop_reason}{_RESET}")
        print(f"{_DIM}  tokens       : {response.input_tokens} in / {response.output_tokens} out{_RESET}")
        if response.text:
            preview = response.text[:200].replace("\n", " ")
            print(f"{_DIM}  text         : {preview!r}{_RESET}")
        for call in response.tool_use_calls:
            print(f"{_DIM}  tool_use     : {call.tool} (id={call.id}){_RESET}")
