"""
Session package — FCP §6.

Public API re-exported for backwards compatibility.
"""

from ..dispatch import dispatch_tool_use
from ..tools import build_tool_declarations as _tool_declarations

from .loop import (
    run_session,
    _CPEBackoff,
    _process_stimulus_and_input,
    _parse_command,
    _make_cycle_fingerprint,
)
from .context import (
    build_boot_context,
    _session_to_turns,
    _rebuild_compact_history,
    _SYSTEM_TYPES,
)
from .history import (
    _drain_and_consolidate,
    _append_msg,
    _return_tool_result,
    _session_byte_size,
    _trim_chat_history,
    _estimate_message_tokens,
)
from .vlog import (
    _vlog,
    _vlog_json,
    _vlog_request,
    _vlog_cycle_summary,
)

__all__ = [
    "run_session",
    "build_boot_context",
    "_session_to_turns",
    "_rebuild_compact_history",
    "_SYSTEM_TYPES",
    "_make_cycle_fingerprint",
    "_parse_command",
    "_CPEBackoff",
    "_process_stimulus_and_input",
    "_drain_and_consolidate",
    "_append_msg",
    "_return_tool_result",
    "_session_byte_size",
    "_trim_chat_history",
    "_estimate_message_tokens",
    "_vlog",
    "_vlog_json",
    "_vlog_request",
    "_vlog_cycle_summary",
]
