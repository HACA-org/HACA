"""
EXEC dispatch — FCP §9.

Entry point for all skill execution requests.  Handles:
  - Skill index lookup and operator-class gate
  - pre_skill / post_skill hooks
  - Action Ledger write-ahead for irreversible skills
  - Subprocess execution (script and text-only skills)
  - Post-execution allowlist approval gates (shell_run, web_fetch)
  - Consecutive failure counters and Reciprocal SIL Watchdog
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any

from ..acp import make as acp_encode
from ..sil import write_notification
from ..store import Layout, read_json
from .allowlist import maybe_prompt_shell_allowlist, maybe_prompt_web_allowlist
from .counters import increment_failure, reset_failure, sil_threshold, last_heartbeat_ts
from .ledger import ledger_write_ahead, ledger_resolve, log_rejected


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class ExecError(Exception):
    """Raised when dispatch cannot proceed."""


class SkillRejected(ExecError):
    """Skill not in index or is operator-class."""


# ---------------------------------------------------------------------------
# Public API
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
    """
    entry = _find_skill(index, skill_name)
    if entry is None:
        log_rejected(layout, skill_name, "not in index")
        from ..hooks import run_hook
        run_hook(layout, "on_skill_rejected", {"skill": skill_name, "reason": "not_in_index"})
        raise SkillRejected(f"Skill not in index: {skill_name!r}")

    skill_class = entry.get("class", "builtin")
    if skill_class == "operator" and not sil_invoked:
        log_rejected(layout, skill_name, "operator-class")
        from ..hooks import run_hook
        run_hook(layout, "on_skill_rejected", {"skill": skill_name, "reason": "operator_class"})
        raise SkillRejected(f"Operator-class skill rejected: {skill_name!r}")

    manifest = _load_manifest(layout, entry)
    timeout = int(manifest.get("timeout_seconds", 30))
    irreversible = bool(manifest.get("irreversible", False))

    from ..hooks import pre_skill_hook, post_skill_hook
    if not pre_skill_hook(layout, skill_name, params, irreversible):
        raise SkillRejected(f"pre_skill hook aborted irreversible skill: {skill_name!r}")

    ledger_seq: int | None = None
    if irreversible and not sil_invoked:
        ledger_seq = ledger_write_ahead(layout, skill_name, params)

    try:
        output = _run_skill(layout, entry, manifest, params, timeout)
    except Exception as exc:
        if ledger_seq is not None:
            ledger_resolve(layout, ledger_seq, "failed")
        increment_failure(layout, skill_name)
        post_skill_hook(layout, skill_name, params, str(exc), failed=True)
        raise

    if skill_name == "shell_run":
        output = maybe_prompt_shell_allowlist(layout, entry, manifest, params, timeout, output)
    elif skill_name == "web_fetch":
        output = maybe_prompt_web_allowlist(layout, entry, manifest, params, timeout, output)

    if ledger_seq is not None:
        ledger_resolve(layout, ledger_seq, "complete")

    reset_failure(layout, skill_name)
    post_skill_hook(layout, skill_name, params, output, failed=False)
    return output


def check_sil_heartbeat(layout: Layout, component: str = "exec") -> bool:
    """Check SIL liveness via last HEARTBEAT record in integrity.log.

    Returns True if SIL is responsive.  If silent beyond sil_threshold_seconds,
    writes SIL_UNRESPONSIVE to operator_notifications/ and returns False.
    """
    threshold = sil_threshold(layout)
    last_hb = last_heartbeat_ts(layout)
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


def _exe_cmd(exe: Path) -> list[str]:
    if exe.suffix == ".py":
        return ["python3", str(exe)]
    return [str(exe)]


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


def _run_text_skill(
    layout: Layout,
    skill_name: str,
    params: dict[str, Any],
    instructions_path: Path,
    timeout: int,
) -> str:
    """Execute a text-only skill by delegating to worker_skill internally."""
    worker_run = layout.skills_lib_dir / "worker_skill" / "run.py"
    if not worker_run.exists():
        raise ExecError(f"worker_skill not available — cannot execute text-only skill {skill_name!r}")

    instructions = instructions_path.read_text(encoding="utf-8")

    task_parts = [f"Execute skill '{skill_name}' with the following parameters:"]
    task_parts.append(json.dumps(params, ensure_ascii=False, indent=2) if params else "(no parameters)")
    task = "\n".join(task_parts)

    context_parts = ["[skill instructions]", instructions, "", "[environment]"]
    workspace_focus_file = layout.root / "state" / "workspace_focus.json"
    if workspace_focus_file.exists():
        try:
            wf = read_json(workspace_focus_file)
            context_parts.append(f"workspace_focus: {wf.get('path', '(unset)')}")
        except Exception:
            context_parts.append("workspace_focus: (unavailable)")
    else:
        context_parts.append("workspace_focus: (not set)")
    context = "\n".join(context_parts)

    manifest_path = instructions_path.parent / "manifest.json"
    skill_desc = ""
    if manifest_path.exists():
        try:
            skill_desc = read_json(manifest_path).get("description", "")
        except Exception:
            pass
    persona = (
        f"You are a precise skill executor for the '{skill_name}' skill.\n{skill_desc}"
        if skill_desc else
        f"You are executing the '{skill_name}' skill. Follow the instructions precisely and return a structured result."
    )

    input_data = json.dumps({
        "skill": "worker_skill",
        "params": {"task": task, "context": context, "persona": persona},
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
