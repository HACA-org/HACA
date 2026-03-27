"""
Action Ledger — FCP §9.

Write-ahead log for irreversible skill executions.  Each irreversible dispatch
records an in_progress entry before the skill runs; on completion or failure the
entry is resolved with the final status.

Also contains result/error envelope writers (_write_skill_result,
_write_skill_error, _log_rejected) and the low-level inbox writer.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from ..acp import make as acp_encode
from ..store import append_jsonl

if TYPE_CHECKING:
    from ..store import Layout


def ledger_write_ahead(layout: "Layout", skill_name: str, params: dict[str, Any]) -> int:
    """Record an in_progress ledger entry. Returns the sequence number (ms timestamp)."""
    seq = int(time.time() * 1000)
    envelope = acp_encode(
        env_type="ACTION_LEDGER",
        source="fcp",
        data={
            "seq": seq,
            "skill": skill_name,
            "params": params,
            "status": "in_progress",
        },
    )
    append_jsonl(layout.session_store, envelope)
    return seq


def ledger_resolve(layout: "Layout", seq: int, status: str) -> None:
    """Resolve a previously written ledger entry with a final status."""
    envelope = acp_encode(
        env_type="ACTION_LEDGER",
        source="fcp",
        data={
            "seq": seq,
            "status": status,
            "resolved_at": int(time.time() * 1000),
        },
    )
    append_jsonl(layout.session_store, envelope)


def write_skill_result(layout: "Layout", skill_name: str, output: str) -> None:
    envelope = acp_encode(
        env_type="SKILL_RESULT",
        source="exec",
        data={"skill": skill_name, "output": output},
    )
    write_inbox(layout, envelope)


def write_skill_error(layout: "Layout", skill_name: str, error: str) -> None:
    envelope = acp_encode(
        env_type="SKILL_ERROR",
        source="exec",
        data={"skill": skill_name, "error": error},
    )
    write_inbox(layout, envelope)


def log_rejected(layout: "Layout", skill_name: str, reason: str) -> None:
    envelope = acp_encode(
        env_type="SKILL_ERROR",
        source="exec",
        data={"skill": skill_name, "error": f"rejected: {reason}"},
    )
    append_jsonl(layout.integrity_log, envelope)


def write_inbox(layout: "Layout", envelope: dict[str, Any]) -> None:
    from ..store import atomic_write
    ts = int(time.time() * 1000)
    env_type = str(envelope.get("type", "msg")).lower()
    dest = layout.inbox_dir / f"{ts}_{env_type}.json"
    atomic_write(dest, envelope)
