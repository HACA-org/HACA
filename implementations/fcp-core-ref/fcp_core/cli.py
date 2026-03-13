"""
CLI entry point — FCP-Core §12.1.

Usage:
  fcp-core <entity-root>
  fcp-core <entity-root> --notifications
  fcp-core <entity-root> decommission --archive | --destroy
"""

from __future__ import annotations

import itertools
import sys
from pathlib import Path


def main() -> None:
    args = sys.argv[1:]
    if not args:
        print("usage: fcp-core <entity-root> [--notifications] [decommission --archive|--destroy]")
        sys.exit(1)

    entity_root = Path(args[0]).resolve()
    rest = list(itertools.islice(args, 1, len(args)))

    from .store import Layout
    layout = Layout(entity_root)

    # --notifications mode: print pending notifications and exit
    if rest and rest[0] == "--notifications":
        from .operator import present_notifications
        present_notifications(layout)
        return

    # decommission mode
    if rest and rest[0] == "decommission":
        _run_decommission(layout, list(itertools.islice(rest, 1, len(rest))))
        return

    # normal boot + session
    _run_normal(layout)


# ---------------------------------------------------------------------------
# Normal boot + session loop
# ---------------------------------------------------------------------------

def _run_normal(layout: "Layout") -> None:
    from .boot import run_boot, BootError
    from .cpe.base import detect_adapter
    from .operator import (
        handle_platform_command,
        present_notifications,
        present_evolution_proposals,
    )
    from .session import run_session, assemble_context
    from .sleep import run_sleep_cycle
    from .store import read_json

    # Boot
    try:
        boot_result = run_boot(layout)
    except BootError as exc:
        print(f"[BOOT FAILED] {exc}")
        sys.exit(1)

    adapter = detect_adapter(boot_result.model)

    # Load sealed skill index
    index: dict = {}
    if layout.skills_index.exists():
        index = read_json(layout.skills_index)

    # Present pending notifications
    present_notifications(layout)

    print(f"[FCP-Core] Entity ready. Type your message or /help.")

    # Session loop
    close_reason = "session_close"
    while True:
        try:
            user_input = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            close_reason = "operator_eof"
            break

        if not user_input:
            continue

        # platform commands
        if user_input.startswith("/"):
            if handle_platform_command(layout, user_input):
                continue
            # check skill alias
            from .operator import resolve_alias
            from .acp import encode as acp_encode
            from .store import append_jsonl
            skill_name = resolve_alias(layout, user_input)
            if skill_name:
                from .exec_ import dispatch, SkillRejected
                parts = user_input.split()
                params = {"args": list(itertools.islice(parts, 1, len(parts)))} if len(parts) > 1 else {}
                try:
                    out = dispatch(layout, skill_name, params, index)
                    print(out)
                except SkillRejected as exc:
                    print(f"[rejected] {exc}")
                continue
            print(f"  unknown command: {user_input}")
            continue

        # inject as MSG and run one cognitive cycle
        from .acp import encode as acp_encode
        from .store import append_jsonl
        envelope = acp_encode(env_type="MSG", source="operator", data=user_input)
        append_jsonl(layout.session_store, envelope)

        close_reason = run_session(layout, adapter, index)
        if close_reason != "operator_eof":
            break

    # Pre-sleep: present evolution proposals
    present_evolution_proposals(layout)

    # Sleep Cycle
    print("[FCP-Core] Running Sleep Cycle...")
    try:
        run_sleep_cycle(layout)
    except Exception as exc:
        print(f"[SLEEP CYCLE ERROR] {exc}")

    print("[FCP-Core] Session complete.")


# ---------------------------------------------------------------------------
# Decommission
# ---------------------------------------------------------------------------

def _run_decommission(layout: "Layout", args: list[str]) -> None:
    from .boot import run_boot, BootError
    from .cpe.base import detect_adapter
    from .acp import encode as acp_encode
    from .operator import present_evolution_proposals
    from .session import run_session
    from .sleep import run_sleep_cycle
    from .store import append_jsonl, read_json

    archive = "--archive" in args
    destroy = "--destroy" in args

    if not archive and not destroy:
        print("decommission requires --archive or --destroy")
        sys.exit(1)

    try:
        boot_result = run_boot(layout)
    except BootError as exc:
        print(f"[BOOT FAILED] {exc}")
        sys.exit(1)

    adapter = detect_adapter(boot_result.model)
    index: dict = {}
    if layout.skills_index.exists():
        index = read_json(layout.skills_index)

    # inject DECOMMISSION envelope
    envelope = acp_encode(
        env_type="MSG",
        source="fcp",
        data={"type": "DECOMMISSION", "mode": "archive" if archive else "destroy"},
    )
    run_session(layout, adapter, index, inject=[envelope])

    present_evolution_proposals(layout)
    run_sleep_cycle(layout)

    if destroy:
        import shutil
        shutil.rmtree(layout.root)
        print("[FCP-Core] Entity destroyed.")
    else:
        print(f"[FCP-Core] Entity archived at {layout.root}.")
