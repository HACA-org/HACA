"""
SIL operator channel — §10.6 / §10.5.

Handles notification writes, operator channel availability check,
and evolution proposal staging.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..acp import make as _acp_make
from ..store import atomic_write
from .utils import utcnow

if TYPE_CHECKING:
    from ..store import Layout


def write_notification(
    layout: "Layout",
    severity: str,
    payload: dict[str, Any],
) -> Path:
    """Write a notification file to state/operator_notifications/.

    Filename format: <utc-timestamp>.<severity>.json
    (colons in timestamp replaced with hyphens per §10.6).

    Returns the path written.
    """
    ts = utcnow().replace(":", "-")
    name = f"{ts}.{severity}.json"
    path = layout.operator_notifications_dir / name
    layout.operator_notifications_dir.mkdir(parents=True, exist_ok=True)
    atomic_write(path, payload)
    return path


def operator_channel_available(layout: "Layout") -> tuple[bool, bool]:
    """Return (notifications_writable, terminal_available)."""
    import sys

    notif_ok = False
    try:
        layout.operator_notifications_dir.mkdir(parents=True, exist_ok=True)
        test = layout.operator_notifications_dir / ".write_test"
        test.write_text("x", encoding="utf-8")
        test.unlink()
        notif_ok = True
    except OSError:
        pass

    terminal_ok = sys.stdin.isatty()
    return notif_ok, terminal_ok


def stage_evolution_proposal(layout: "Layout", content: str) -> Path:
    """Write a PROPOSAL_PENDING notification and return its path."""
    ts = int(time.time() * 1000)
    envelope = _acp_make(
        env_type="MSG",
        source="sil",
        data={"type": "PROPOSAL_PENDING", "content": content, "ts": ts},
    )
    dest = layout.operator_notifications_dir / f"{ts}_proposal_pending.json"
    tmp = dest.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(envelope, indent=2), encoding="utf-8")
    os.replace(tmp, dest)
    return dest
