"""
Vital Check — FCP §10.3.

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

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .formats import StructuralBaseline
from .sil import log_critical, log_heartbeat, log_severance_commit, sha256_file as _sha256_file, write_notification
from .store import Layout, atomic_write, read_json


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
    _check_skill_audit(layout)

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
    focus_path: Path | None = None
    workspace: Path | None = None
    try:
        wf = read_json(layout.workspace_focus)
        raw_path = wf.get("path", "")
        if not raw_path:
            return []
        focus_path = Path(str(raw_path)).resolve()
        workspace = layout.workspace_dir.resolve()
        focus_path.relative_to(workspace)
    except ValueError:
        detail = {
            "path": str(focus_path) if focus_path else "",
            "workspace": str(workspace) if workspace else "",
        }
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
# Check 5 — Skill audit (hash vs Integrity Document)
# ---------------------------------------------------------------------------

def _check_skill_audit(layout: Layout) -> None:
    """Check skill executables against the Integrity Document.

    For each tracked skill file whose hash diverges:
      - Remove the skill entry from skills/index.json
      - Emit SEVERANCE_COMMIT to integrity.log
      - Notify Operator
    """
    if not layout.integrity_doc.exists() or not layout.skills_index.exists():
        return
    try:
        doc = read_json(layout.integrity_doc)
        tracked: dict[str, str] = doc.get("files", {})
        index = read_json(layout.skills_index)
    except Exception:
        return

    skills: list[dict] = index.get("skills", [])
    removed: list[str] = []

    for entry in list(skills):
        skill_name = entry.get("name", "")
        manifest_rel = entry.get("manifest", "")
        if not manifest_rel:
            continue
        manifest_path = layout.root / manifest_rel
        exe_path = manifest_path.parent / "run.py"
        exe_rel = str(exe_path.relative_to(layout.root))
        if not exe_path.is_file():
            continue
        expected = tracked.get(exe_rel)
        if expected is None:
            continue  # not tracked — skip
        actual = _sha256_file(exe_path)
        if actual != expected:
            issues = [f"hash mismatch: expected {expected}, got {actual}"]
            # Remove from index
            skills.remove(entry)
            removed.append(skill_name)
            # Log and notify
            log_severance_commit(layout, skill_name, issues)
            write_notification(layout, "warning", {
                "type": "SEVERANCE_COMMIT",
                "skill": skill_name,
                "issues": issues,
            })

    if removed:
        index["skills"] = skills
        atomic_write(layout.skills_index, index)


# ---------------------------------------------------------------------------
# Check 4 — Identity Drift (persona hash vs Integrity Document)
# ---------------------------------------------------------------------------

def _check_identity_drift(layout: Layout) -> list[str]:
    """Check persona files against Integrity Document.

    HACA-Core: any drift → IDENTITY_DRIFT Critical immediately.
    HACA-Evolve: drift → IDENTITY_DEGRADED warning; if a prior IDENTITY_DEGRADED
                 was already recorded this session, escalate to Critical.
    """
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
            continue
        actual = _sha256_file(persona_file)
        if actual != expected:
            drifted.append(rel)

    if not drifted:
        return []

    detail = {"drifted_files": drifted}

    # Check profile
    baseline_raw: dict = {}
    try:
        baseline_raw = read_json(layout.baseline)
    except Exception:
        pass
    profile = baseline_raw.get("profile", "haca-core")

    if profile == "haca-evolve":
        # Check if IDENTITY_DEGRADED was already emitted — escalate if so
        degraded_sentinel = layout.root / "state" / "sentinels" / "identity_degraded"
        if degraded_sentinel.exists():
            # Already degraded — escalate to Critical
            degraded_sentinel.unlink(missing_ok=True)
            log_critical(layout, "IDENTITY_DRIFT", detail)
            write_notification(layout, "critical", {
                "type": "IDENTITY_DRIFT",
                "detail": detail,
            })
            return ["identity_drift"]
        else:
            # First occurrence — Degraded warning, set sentinel
            degraded_sentinel.touch()
            write_notification(layout, "warning", {
                "type": "IDENTITY_DEGRADED",
                "detail": detail,
            })
            return ["identity_degraded"]
    else:
        # HACA-Core: zero tolerance
        log_critical(layout, "IDENTITY_DRIFT", detail)
        write_notification(layout, "critical", {
            "type": "IDENTITY_DRIFT",
            "detail": detail,
        })
        return ["identity_drift"]


