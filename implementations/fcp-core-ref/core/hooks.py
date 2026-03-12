"""Hook runner — FCP-Core lifecycle hooks.

Hooks are shell scripts placed in hooks/<event>/<name>.sh.
All scripts in a given event directory are executed in lexicographic order.
A non-zero exit code logs a warning but never blocks entity operation.

Supported events
----------------
on_boot             — after boot, before first CPE cycle
on_session_close    — after closure_payload, before Endure
pre_skill           — before EXEC runs a skill
post_skill          — after EXEC completes a skill
post_endure         — after Endure Protocol run

Common env vars (all events)
-----------------------------
FCP_ENTITY_ROOT     entity root path
FCP_SESSION_ID      current session ID
FCP_HOOK_EVENT      event name

Event-specific env vars
------------------------
pre_skill   FCP_SKILL_NAME, FCP_SKILL_PARAMS (JSON)
post_skill  FCP_SKILL_NAME, FCP_SKILL_STATUS  (success | error | timeout)
post_endure FCP_ENDURE_COMMITS  (number of commits applied)
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_HOOK_TIMEOUT = 10  # seconds per script


def run_hook(
    entity_root: Path,
    event:       str,
    session_id:  str = "",
    extra_env:   dict[str, str] | None = None,
) -> None:
    """Run all *.sh scripts in ``hooks/<event>/`` in lexicographic order.

    Silently skips absent event directories.  Non-zero exit or timeout
    prints a warning to stderr and continues.
    """
    hook_dir = entity_root / "hooks" / event
    if not hook_dir.is_dir():
        return

    scripts = sorted(hook_dir.glob("*.sh"))
    if not scripts:
        return

    env = {
        **os.environ,
        "FCP_ENTITY_ROOT": str(entity_root),
        "FCP_SESSION_ID":  session_id,
        "FCP_HOOK_EVENT":  event,
        **(extra_env or {}),
    }

    for script in scripts:
        try:
            result = subprocess.run(
                ["/bin/bash", str(script)],
                env=env,
                timeout=_HOOK_TIMEOUT,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                detail = (result.stderr.strip() or result.stdout.strip())[:200]
                print(
                    f"[HOOK] {event}/{script.name} exited {result.returncode}"
                    + (f": {detail}" if detail else ""),
                    file=sys.stderr,
                )
        except subprocess.TimeoutExpired:
            print(
                f"[HOOK] {event}/{script.name} timed out ({_HOOK_TIMEOUT}s)",
                file=sys.stderr,
            )
        except Exception as exc:
            print(f"[HOOK] {event}/{script.name} error: {exc}", file=sys.stderr)
