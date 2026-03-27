"""
Lifecycle Hooks — FCP §9.7.

Executes scripts in hooks/<event>/ in sorted order.
Hook failure never aborts the triggering operation — logged and continues.

Events:
  on_boot          — after Phase 7 (session token issued)
  on_session_close — before Sleep Cycle
  pre_skill        — before skill dispatch
  post_skill       — after skill dispatch
  post_endure      — after Stage 3 of Sleep Cycle

Environment passed to each hook script:
  FCP_EVENT         — event name
  FCP_ENTITY_ROOT   — absolute path to entity root
  FCP_SESSION_TOKEN — session_id from active token (empty if absent)
  FCP_EVENT_DATA    — JSON string with event-specific data

Exit code:
  0       — success
  non-0   — failure; logged; for pre_skill on irreversible skills → aborts dispatch
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

from .store import Layout, read_json


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_hook(
    layout: Layout,
    event: str,
    data: dict[str, Any] | None = None,
) -> bool:
    """Run all executable scripts in hooks/<event>/ in sorted order.

    Returns True if all hooks succeeded (or none exist).
    Returns False if any hook failed.
    Failure is always logged; never raises.
    """
    hook_dir = layout.hooks_dir / event
    if not hook_dir.is_dir():
        return True

    scripts = sorted(
        p for p in hook_dir.iterdir()
        if p.is_file() and os.access(p, os.X_OK)
    )
    if not scripts:
        return True

    timeout = _hook_timeout(layout)
    session_token = _read_session_id(layout)
    env = _build_env(event, layout, session_token, data or {})

    all_ok = True
    for script in scripts:
        ok = _run_script(layout, script, env, timeout)
        if not ok:
            all_ok = False

    return all_ok


def pre_skill_hook(
    layout: Layout,
    skill_name: str,
    params: dict[str, Any],
    irreversible: bool,
) -> bool:
    """Run pre_skill hooks.

    Returns True if dispatch should proceed.
    If irreversible=True and any hook fails, returns False (dispatch aborted).
    If irreversible=False, always returns True (failure only logged).
    """
    data = {"skill": skill_name, "params": params, "irreversible": irreversible}
    ok = run_hook(layout, "pre_skill", data)
    if not ok and irreversible:
        _log(layout, "pre_skill", f"hook failed for irreversible skill {skill_name!r} — dispatch aborted")
        return False
    return True


def post_skill_hook(
    layout: Layout,
    skill_name: str,
    params: dict[str, Any],
    output: str,
    failed: bool,
) -> None:
    data = {"skill": skill_name, "params": params, "failed": failed, "output": output[:512]}
    run_hook(layout, "post_skill", data)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _run_script(
    layout: Layout,
    script: Path,
    env: dict[str, str],
    timeout: int,
) -> bool:
    try:
        result = subprocess.run(
            [str(script)],
            env=env,
            timeout=timeout,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip()
            _log(layout, script.parent.name, f"{script.name} exited {result.returncode}: {detail[:256]}")
            return False
        return True
    except subprocess.TimeoutExpired:
        _log(layout, script.parent.name, f"{script.name} timed out after {timeout}s")
        return False
    except Exception as exc:
        _log(layout, script.parent.name, f"{script.name} error: {exc}")
        return False


def _build_env(
    event: str,
    layout: Layout,
    session_token: str,
    data: dict[str, Any],
) -> dict[str, str]:
    env = os.environ.copy()
    env["FCP_EVENT"] = event
    env["FCP_ENTITY_ROOT"] = str(layout.root)
    env["FCP_SESSION_TOKEN"] = session_token
    env["FCP_EVENT_DATA"] = json.dumps(data)
    return env


def _read_session_id(layout: Layout) -> str:
    try:
        if layout.session_token.exists():
            return str(read_json(layout.session_token).get("session_id", ""))
    except Exception:
        pass
    return ""


def _hook_timeout(layout: Layout) -> int:
    try:
        baseline = read_json(layout.baseline)
        return int(baseline.get("hooks", {}).get("timeout_seconds", 10))
    except Exception:
        return 10


def _log(layout: Layout, event: str, message: str) -> None:
    try:
        ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        line = f"{ts} HOOK_FAIL [{event}] {message}\n"
        log_path = layout.integrity_log
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass
