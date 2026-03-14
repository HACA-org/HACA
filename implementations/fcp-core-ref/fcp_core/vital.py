"""
Vital Check — FCP-Core §10.3.

Runs on two triggers (whichever comes first):
  - cycle_threshold T completed Cognitive Cycles since last check
  - interval_seconds I elapsed since last check

Checks performed:
  1. Context budget — tokens_used / budget_tokens >= critical_pct → Critical
  2. workspace_focus path outside workspace/ → Critical
  3. Pre-session buffer above max_entries → operator notification
  4. Identity Drift — persona hash vs Integrity Document → Critical
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .formats import StructuralBaseline
from .sil import log_critical, log_heartbeat, write_notification
from .store import Layout, read_json


# ---------------------------------------------------------------------------
# State tracker — one instance per session
# ---------------------------------------------------------------------------

@dataclass
class VitalCheckState:
    cycles_since_check: int = 0
    last_check_ts: float = field(default_factory=time.time)
    session_id: str = ""


def should_run(state: VitalCheckState, baseline: StructuralBaseline) -> bool:
    """Return True if either trigger threshold has been reached."""
    cycle_due = state.cycles_since_check >= baseline.heartbeat_cycle_threshold
    time_due = (time.time() - state.last_check_ts) >= baseline.heartbeat_interval_seconds
    return cycle_due or time_due


def tick(state: VitalCheckState) -> None:
    """Increment cycle counter — call after each completed Cognitive Cycle."""
    state.cycles_since_check += 1


def run(
    layout: Layout,
    baseline: StructuralBaseline,
    state: VitalCheckState,
    tokens_used: int,
) -> list[str]:
    """Execute all Vital Checks. Returns list of Critical condition names raised.

    Resets the state counters after running regardless of outcome.
    Logs a HEARTBEAT entry to integrity.log.
    """
    criticals: list[str] = []

    criticals += _check_context_budget(layout, baseline, tokens_used)
    criticals += _check_workspace_focus(layout)
    _check_presession_buffer(layout, baseline)
    criticals += _check_identity_drift(layout)

    log_heartbeat(layout, state.session_id)

    # reset counters
    state.cycles_since_check = 0
    state.last_check_ts = time.time()

    return criticals


# ---------------------------------------------------------------------------
# Check 1 — Context budget
# ---------------------------------------------------------------------------

def _check_context_budget(
    layout: Layout,
    baseline: StructuralBaseline,
    tokens_used: int,
) -> list[str]:
    budget = baseline.context_window_budget_tokens
    critical_pct = baseline.context_window_critical_pct
    if budget <= 0:
        return []
    pct = int(tokens_used * 100 / budget)
    if pct >= critical_pct:
        detail = {"tokens_used": tokens_used, "budget": budget, "pct": pct, "threshold_pct": critical_pct}
        log_critical(layout, "CONTEXT_BUDGET_CRITICAL", detail)
        write_notification(layout, "critical", {
            "type": "CONTEXT_BUDGET_CRITICAL",
            "detail": detail,
        })
        return ["context_budget"]
    return []


# ---------------------------------------------------------------------------
# Check 2 — workspace_focus path
# ---------------------------------------------------------------------------

def _check_workspace_focus(layout: Layout) -> list[str]:
    if not layout.workspace_focus.exists():
        return []
    try:
        wf = read_json(layout.workspace_focus)
        focus_path = Path(str(wf.get("path", ""))).resolve()
        workspace = layout.workspace_dir.resolve()
        focus_path.relative_to(workspace)
    except ValueError:
        detail = {"path": str(focus_path), "workspace": str(workspace)}
        log_critical(layout, "WORKSPACE_FOCUS_INVALID", detail)
        write_notification(layout, "critical", {
            "type": "WORKSPACE_FOCUS_INVALID",
            "detail": detail,
        })
        return ["workspace_focus_invalid"]
    except Exception:
        pass
    return []


# ---------------------------------------------------------------------------
# Check 3 — Pre-session buffer
# ---------------------------------------------------------------------------

def _check_presession_buffer(layout: Layout, baseline: StructuralBaseline) -> None:
    if not layout.presession_dir.exists():
        return
    entries = list(layout.presession_dir.iterdir())
    count = len(entries)
    max_entries = baseline.pre_session_buffer_max_entries
    if count > max_entries:
        write_notification(layout, "warning", {
            "type": "PRESESSION_BUFFER_OVERFLOW",
            "detail": {"count": count, "max_entries": max_entries},
        })


# ---------------------------------------------------------------------------
# Check 4 — Identity Drift (persona hash vs Integrity Document)
# ---------------------------------------------------------------------------

def _check_identity_drift(layout: Layout) -> list[str]:
    if not layout.integrity_doc.exists():
        return []
    try:
        doc = read_json(layout.integrity_doc)
        tracked: dict[str, str] = doc.get("files", {})
    except Exception:
        return []

    drifted: list[str] = []
    if not layout.persona_dir.exists():
        return []

    for persona_file in sorted(layout.persona_dir.iterdir()):
        if not persona_file.is_file():
            continue
        rel = str(persona_file.relative_to(layout.root))
        expected = tracked.get(rel)
        if expected is None:
            continue  # not tracked — skip
        actual = _sha256_file(persona_file)
        if actual != expected:
            drifted.append(rel)

    if drifted:
        detail = {"drifted_files": drifted}
        log_critical(layout, "IDENTITY_DRIFT", detail)
        write_notification(layout, "critical", {
            "type": "IDENTITY_DRIFT",
            "detail": detail,
        })
        return ["identity_drift"]
    return []


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return f"sha256:{h.hexdigest()}"
