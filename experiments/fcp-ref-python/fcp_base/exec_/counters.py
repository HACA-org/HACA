"""
Consecutive failure counters and config helpers — FCP §9.

Tracks per-skill failure counts in state/exec_counters.json.  When a skill
exceeds the n_retry threshold a SIL notification is written.  On success the
counter is reset.

Also contains the config readers (_sil_threshold, _n_retry, _last_heartbeat_ts)
used by the watchdog and dispatch.
"""

from __future__ import annotations

import json
import os
import time
from typing import TYPE_CHECKING, Any

from ..acp import make as acp_encode
from ..store import read_json

if TYPE_CHECKING:
    from ..store import Layout


# ---------------------------------------------------------------------------
# Failure tracking
# ---------------------------------------------------------------------------

def failure_key(skill_name: str) -> str:
    return f"_fail_{skill_name}"


def increment_failure(layout: "Layout", skill_name: str) -> None:
    counter = read_counters(layout)
    key = failure_key(skill_name)
    count = int(counter.get(key, 0)) + 1
    counter[key] = count
    write_counters(layout, counter)

    n = n_retry(layout)
    if count >= n:
        from ..sil import write_notification
        envelope = acp_encode(
            env_type="SKILL_ERROR",
            source="exec",
            data={"skill": skill_name, "error": f"exceeded n_retry ({n})"},
        )
        write_notification(layout, envelope["type"].lower(), envelope)


def reset_failure(layout: "Layout", skill_name: str) -> None:
    counter = read_counters(layout)
    key = failure_key(skill_name)
    if key in counter:
        write_counters(layout, {k: v for k, v in counter.items() if k != key})


def read_counters(layout: "Layout") -> dict[str, Any]:
    p = layout.state_dir / "exec_counters.json"
    if not p.exists():
        return {}
    try:
        return read_json(p)
    except Exception:
        return {}


def write_counters(layout: "Layout", data: dict[str, Any]) -> None:
    p = layout.state_dir / "exec_counters.json"
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, p)


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def sil_threshold(layout: "Layout") -> float:
    try:
        baseline = read_json(layout.baseline)
        return float(baseline.get("watchdog", {}).get("sil_threshold_seconds", 60))
    except Exception:
        return 60.0


def n_retry(layout: "Layout") -> int:
    try:
        baseline = read_json(layout.baseline)
        return int(baseline.get("fault", {}).get("n_retry", 3))
    except Exception:
        return 3


def last_heartbeat_ts(layout: "Layout") -> float | None:
    """Return Unix timestamp of the last HEARTBEAT in integrity.log, or None."""
    if not layout.integrity_log.exists():
        return None
    last: float | None = None
    for line in layout.integrity_log.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
            if rec.get("type") == "HEARTBEAT":
                ts = rec.get("ts")
                if ts is not None:
                    last = float(ts)
        except Exception:
            continue
    return last
