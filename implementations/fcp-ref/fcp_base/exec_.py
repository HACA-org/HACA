"""
EXEC — Execution Layer.  FCP §9

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

from .acp import make as acp_encode
from .sil import write_notification
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
        from .hooks import run_hook
        run_hook(layout, "on_skill_rejected", {"skill": skill_name, "reason": "not_in_index"})
        raise SkillRejected(f"Skill not in index: {skill_name!r}")

    skill_class = entry.get("class", "builtin")
    if skill_class == "operator" and not sil_invoked:
        _log_rejected(layout, skill_name, "operator-class")
        from .hooks import run_hook
        run_hook(layout, "on_skill_rejected", {"skill": skill_name, "reason": "operator_class"})
        raise SkillRejected(f"Operator-class skill rejected: {skill_name!r}")

    manifest = _load_manifest(layout, entry)
    timeout = int(manifest.get("timeout_seconds", 30))
    irreversible = bool(manifest.get("irreversible", False))

    # pre_skill hook
    from .hooks import pre_skill_hook, post_skill_hook
    if not pre_skill_hook(layout, skill_name, params, irreversible):
        raise SkillRejected(f"pre_skill hook aborted irreversible skill: {skill_name!r}")

    ledger_seq: int | None = None
    if irreversible and not sil_invoked:
        ledger_seq = _ledger_write_ahead(layout, skill_name, params)

    try:
        output = _run_skill(layout, entry, manifest, params, timeout)
    except Exception as exc:
        if ledger_seq is not None:
            _ledger_resolve(layout, ledger_seq, "failed")
        _increment_failure(layout, skill_name)
        post_skill_hook(layout, skill_name, params, str(exc), failed=True)
        raise

    if ledger_seq is not None:
        _ledger_resolve(layout, ledger_seq, "complete")

    _reset_failure(layout, skill_name)
    post_skill_hook(layout, skill_name, params, output, failed=False)
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
    write_notification(layout, envelope["type"].lower(), envelope)
    return False


# ---------------------------------------------------------------------------
# Internal: skill lookup and execution
# ---------------------------------------------------------------------------

def _run_text_skill(
    layout: Layout,
    skill_name: str,
    params: dict[str, Any],
    instructions_path: Path,
    timeout: int,
) -> str:
    """Execute a text-only skill by delegating to worker_skill internally."""
    instructions = instructions_path.read_text(encoding="utf-8")
    context_parts = [f"Skill: {skill_name}"]
    if params:
        context_parts.append(f"Parameters: {json.dumps(params, ensure_ascii=False)}")
    context = "\n".join(context_parts)

    worker_entry = _find_skill({"skills": [
        {"name": "worker_skill", "class": "builtin", "manifest": f"skills/lib/worker_skill/manifest.json"}
    ]}, "worker_skill")
    # locate worker_skill run.py directly
    worker_run = layout.skills_lib_dir / "worker_skill" / "run.py"
    if not worker_run.exists():
        raise ExecError(f"worker_skill not available — cannot execute text-only skill {skill_name!r}")

    input_data = json.dumps({
        "skill": "worker_skill",
        "params": {
            "task": instructions,
            "context": context,
            "persona": f"You are executing the '{skill_name}' skill. Follow the instructions precisely and return a structured result.",
        },
        "entity_root": str(layout.root),
    })

    result = subprocess.run(
        ["python3", str(worker_run)],
        input=input_data,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(layout.root),
    )

    if result.returncode != 0:
        raise ExecError(result.stdout.strip() or result.stderr.strip() or f"text skill exited {result.returncode}")
    return result.stdout


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
        execution = manifest.get("execution", "script")
        if execution == "text":
            instructions_file = manifest.get("instructions", "README.md")
            instructions_path = exe_dir / instructions_file
            if not instructions_path.exists():
                raise ExecError(
                    f"Text-only skill {skill_name!r}: instructions file "
                    f"{instructions_file!r} not found in {exe_dir}"
                )
            return _run_text_skill(layout, skill_name, params, instructions_path, timeout)
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
        raise ExecError(result.stdout.strip() or result.stderr.strip() or f"skill exited {result.returncode}")

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
        write_notification(layout, envelope["type"].lower(), envelope)


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
    from .store import atomic_write
    ts = int(time.time() * 1000)
    env_type = str(envelope.get("type", "msg")).lower()
    dest = layout.inbox_dir / f"{ts}_{env_type}.json"
    atomic_write(dest, envelope)


