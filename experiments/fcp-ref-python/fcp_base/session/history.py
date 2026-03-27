"""
Session history helpers — bounded growth, drain/consolidate, append helpers.
"""

from __future__ import annotations

import json
from typing import Any

from ..acp import drain_inbox, make as acp_encode
from ..store import Layout, append_jsonl


# ---------------------------------------------------------------------------
# Chat History Management — Bounded Growth
# ---------------------------------------------------------------------------

def _estimate_message_tokens(msg: dict[str, Any]) -> int:
    """Estimate token count for a single message.

    Uses character-based heuristic: ~4 chars per token (rough average).
    """
    content = msg.get("content", "")
    return max(1, len(content) // 4)


def _trim_chat_history(
    chat_history: list[dict[str, Any]],
    max_messages: int | None = None,
    target_tokens: int | None = None,
) -> None:
    """Trim chat history by removing oldest non-critical messages.

    Keeps initial boot context (first message) and recent messages.
    Removes from oldest to newest until constraints are met.

    Args:
        chat_history: In-place list to trim
        max_messages: Max number of messages to keep (None = no limit)
        target_tokens: Target token count (drop oldest until under this)
    """
    if not chat_history:
        return

    # Keep first message (boot context)
    if len(chat_history) <= 1:
        return

    if max_messages and len(chat_history) > max_messages:
        # Drop oldest non-first messages
        excess = len(chat_history) - max_messages
        for _ in range(excess):
            if len(chat_history) > 1:
                chat_history.pop(1)  # Remove 2nd message (first is boot context)

    if target_tokens:
        # Calculate current token count
        current_tokens = sum(_estimate_message_tokens(msg) for msg in chat_history)

        # Drop oldest messages until under target
        while current_tokens > target_tokens and len(chat_history) > 1:
            removed = chat_history.pop(1)  # Remove 2nd message (first is boot context)
            current_tokens -= _estimate_message_tokens(removed)


# ---------------------------------------------------------------------------
# Inbox drain and session store helpers
# ---------------------------------------------------------------------------

def _drain_and_consolidate(layout: Layout) -> list[dict[str, Any]]:
    import dataclasses
    envelopes = drain_inbox(layout.inbox_dir)
    result = []
    for env in envelopes:
        d = dataclasses.asdict(env) if dataclasses.is_dataclass(env) else env
        append_jsonl(layout.session_store, d)
        result.append(d)
    return result


def _append_msg(layout: Layout, source: str, text: str) -> None:
    envelope = acp_encode(env_type="MSG", source=source, data=text)
    append_jsonl(layout.session_store, envelope)


def _return_tool_result(
    layout: Layout, call_id: str, tool: str, result: dict[str, Any]
) -> int:
    """Write tool result to session.jsonl and return its numeric timestamp (ms)."""
    import time as _time
    ts_ms = int(_time.time() * 1000)
    envelope = acp_encode(
        env_type="MSG",
        source="fcp",
        data={"tool_result": {"tool_use_id": call_id, "tool": tool,
                              "content": result, "_ts_ms": ts_ms}},
    )
    append_jsonl(layout.session_store, envelope)
    return ts_ms


def _session_byte_size(layout: Layout) -> int:
    if not layout.session_store.exists():
        return 0
    return layout.session_store.stat().st_size
