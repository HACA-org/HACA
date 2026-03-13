"""
EXEC — Execution Layer.  FCP-Core §9

Dispatches skill requests against skills/index.json (no per-execution re-validation).
Manages the Action Ledger for irreversible skills.
Manages consecutive failure counters and Reciprocal SIL Watchdog.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any

from .acp import encode as acp_encode
from .store import Layout, append_jsonl, read_json


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class ExecError(Exception):
    """Raised when dispatch cannot proceed (index miss, operator-class, etc.)."""


class SkillRejected(ExecError):
    """Skill not in index or is operator-class."""


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

def dispatch(
    layout: Layout,
    skill_name: str,
    params: dict[str, Any],
    index: dict[str, Any],
    *,
    sil_invoked: bool = False,
) -> str:
    """Dispatch a skill request against the sealed Skill Index.

    Returns the skill's stdout output as a string.

    Raises SkillRejected if the skill is absent from index or is operator-class
    (unless sil_invoked=True, which bypasses operator-class check for SIL workers).

    Action Ledger write-ahead is performed for irreversible skills before
    dispatch; the entry is resolved after the skill returns.
    """
    entry = _find_skill(index, skill_name)
    if entry is None:
        _log_rejected(layout, skill_name, "not in index")
        raise SkillRejected(f"Skill not in index: {skill_name!r}")

    skill_class = entry.get("class", "builtin")
    if skill_class == "operator" and not sil_invoked:
        _log_rejected(layout, skill_name, "operator-class")
        raise SkillRejected(f"Operator-class skill rejected: {skill_name!r}")

    manifest = _load_manifest(layout, entry)
    timeout = int(manifest.get("timeout_seconds", 30))
    irreversible = bool(manifest.get("irreversible", False))

    ledger_seq: int | None = None
    if irreversible and not sil_invoked:
        ledger_seq = _ledger_write_ahead(layout, skill_name, params)

    try:
        output = _run_skill(layout, entry, manifest, params, timeout)
    except Exception as exc:
        if ledger_seq is not None:
            _ledger_resolve(layout, ledger_seq, "failed")
        _write_skill_error(layout, skill_name, str(exc))
        _increment_failure(layout, skill_name)
        raise

    if ledger_seq is not None:
        _ledger_resolve(layout, ledger_seq, "complete")

    _reset_failure(layout, skill_name)
    _write_skill_result(layout, skill_name, output)
    return output


# ---------------------------------------------------------------------------
# Reciprocal SIL Watchdog
# ---------------------------------------------------------------------------

def check_sil_heartbeat(layout: Layout, component: str = "exec") -> bool:
    """Check SIL liveness via last HEARTBEAT record in integrity.log.

    Returns True if SIL is responsive.  If silent beyond sil_threshold_seconds,
    writes SIL_UNRESPONSIVE to operator_notifications/ and returns False.
    Caller must activate Passive Distress Beacon and halt.
    """
    threshold = _sil_threshold(layout)
    last_hb = _last_heartbeat_ts(layout)
    if last_hb is None:
        return True  # no heartbeat yet — not yet in session, skip check

    elapsed = time.time() - last_hb
    if elapsed <= threshold:
        return True

    envelope = acp_encode(
        env_type="SIL_UNRESPONSIVE",
        source=component,
        data={
            "component": component,
            "last_heartbeat": last_hb,
            "elapsed_seconds": elapsed,
            "threshold_seconds": threshold,
        },
    )
    _write_operator_notification(layout, envelope)
    return False


# ---------------------------------------------------------------------------
# Internal: skill lookup and execution
# ---------------------------------------------------------------------------

def _exe_cmd(exe: Path) -> list[str]:
    if exe.suffix == ".py":
        return ["python3", str(exe)]
    return [str(exe)]


def _find_skill(index: dict[str, Any], name: str) -> dict[str, Any] | None:
    for entry in index.get("skills", []):
        if entry.get("name") == name:
            return entry
    return None


def _load_manifest(layout: Layout, entry: dict[str, Any]) -> dict[str, Any]:
    rel = entry.get("manifest", "")
    path = layout.root / rel
    if not path.exists():
        return {}
    return read_json(path)


def _run_skill(
    layout: Layout,
    entry: dict[str, Any],
    manifest: dict[str, Any],
    params: dict[str, Any],
    timeout: int,
) -> str:
    """Locate and execute the skill executable, passing params via stdin."""
    skill_name = entry.get("name", "")
    skill_class = entry.get("class", "builtin")

    if skill_class in ("builtin", "operator"):
        exe_dir = layout.skills_lib_dir / skill_name
    else:
        exe_dir = layout.skills_dir / skill_name

    # find executable: run.py preferred, then run.sh, then run
    exe: Path | None = None
    for candidate in ("run.py", "run.sh", "run"):
        p = exe_dir / candidate
        if p.exists():
            exe = p
            break

    if exe is None:
        raise ExecError(f"No executable found for skill {skill_name!r} in {exe_dir}")

    cmd = _exe_cmd(Path(str(exe)))

    input_data = json.dumps({
        "skill": skill_name,
        "params": params,
        "entity_root": str(layout.root),
    })

    result = subprocess.run(
        cmd,
        input=input_data,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(layout.root),
    )

    if result.returncode != 0:
        raise ExecError(result.stderr.strip() or f"skill exited {result.returncode}")

    return result.stdout


# ---------------------------------------------------------------------------
# Internal: Action Ledger
# ---------------------------------------------------------------------------

def _ledger_write_ahead(layout: Layout, skill_name: str, params: dict[str, Any]) -> int:
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


def _ledger_resolve(layout: Layout, seq: int, status: str) -> None:
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


# ---------------------------------------------------------------------------
# Internal: result/error envelopes
# ---------------------------------------------------------------------------

def _write_skill_result(layout: Layout, skill_name: str, output: str) -> None:
    envelope = acp_encode(
        env_type="SKILL_RESULT",
        source="exec",
        data={"skill": skill_name, "output": output},
    )
    _write_inbox(layout, envelope)


def _write_skill_error(layout: Layout, skill_name: str, error: str) -> None:
    envelope = acp_encode(
        env_type="SKILL_ERROR",
        source="exec",
        data={"skill": skill_name, "error": error},
    )
    _write_inbox(layout, envelope)


def _log_rejected(layout: Layout, skill_name: str, reason: str) -> None:
    envelope = acp_encode(
        env_type="SKILL_ERROR",
        source="exec",
        data={"skill": skill_name, "error": f"rejected: {reason}"},
    )
    append_jsonl(layout.integrity_log, envelope)


# ---------------------------------------------------------------------------
# Internal: consecutive failure tracking
# ---------------------------------------------------------------------------

def _failure_key(skill_name: str) -> str:
    return f"_fail_{skill_name}"


def _increment_failure(layout: Layout, skill_name: str) -> None:
    counter = _read_counters(layout)
    key = _failure_key(skill_name)
    count = int(counter.get(key, 0)) + 1
    counter[key] = count
    _write_counters(layout, counter)

    n_retry = _n_retry(layout)
    if count >= n_retry:
        envelope = acp_encode(
            env_type="SKILL_ERROR",
            source="exec",
            data={"skill": skill_name, "error": f"exceeded n_retry ({n_retry})"},
        )
        _write_operator_notification(layout, envelope)


def _reset_failure(layout: Layout, skill_name: str) -> None:
    counter = _read_counters(layout)
    key = _failure_key(skill_name)
    if key in counter:
        _write_counters(layout, {k: v for k, v in counter.items() if k != key})


def _read_counters(layout: Layout) -> dict[str, Any]:
    p = layout.state_dir / "exec_counters.json"
    if not p.exists():
        return {}
    try:
        return read_json(p)
    except Exception:
        return {}


def _write_counters(layout: Layout, data: dict[str, Any]) -> None:
    import os
    p = layout.state_dir / "exec_counters.json"
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, p)


# ---------------------------------------------------------------------------
# Internal: config helpers
# ---------------------------------------------------------------------------

def _sil_threshold(layout: Layout) -> float:
    try:
        baseline = read_json(layout.baseline)
        return float(baseline.get("watchdog", {}).get("sil_threshold_seconds", 60))
    except Exception:
        return 60.0


def _n_retry(layout: Layout) -> int:
    try:
        baseline = read_json(layout.baseline)
        return int(baseline.get("fault", {}).get("n_retry", 3))
    except Exception:
        return 3


def _last_heartbeat_ts(layout: Layout) -> float | None:
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


# ---------------------------------------------------------------------------
# Internal: I/O helpers
# ---------------------------------------------------------------------------

def _write_inbox(layout: Layout, envelope: dict[str, Any]) -> None:
    import os
    ts = int(time.time() * 1000)
    env_type = str(envelope.get("type", "msg")).lower()
    dest = layout.inbox_dir / f"{ts}_{env_type}.json"
    tmp = dest.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(envelope, indent=2), encoding="utf-8")
    os.replace(tmp, dest)


def _write_operator_notification(layout: Layout, envelope: dict[str, Any]) -> None:
    import os
    ts = int(time.time() * 1000)
    env_type = str(envelope.get("type", "notif")).lower()
    dest = layout.operator_notifications_dir / f"{ts}_{env_type}.json"
    tmp = dest.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(envelope, indent=2), encoding="utf-8")
    os.replace(tmp, dest)
