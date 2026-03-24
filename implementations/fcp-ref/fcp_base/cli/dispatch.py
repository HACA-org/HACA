"""
CLI entry point and command routing — FCP §12.1.

Usage:
  fcp                          — boot default entity, workspace_focus = cwd
  fcp init                     — create or update an entity in ~/.fcp/<entity_id>/
  fcp list                     — list installed entities
  fcp set <entity_id>          — set default entity
  fcp doctor [--fix]           — check/repair without booting
  fcp decommission --archive | --destroy
"""

from __future__ import annotations

import sys
from pathlib import Path

from ..store import (
    Layout, load_env_file,
    get_default_entity, set_default_entity, list_entities, entity_root_for,
)
from .. import ui
from .commands import (
    run_normal,
    run_auto,
    run_update,
    run_doctor,
    run_decommission,
    run_model,
    run_status,
    run_agenda,
)
from .endure import run_endure_sync, run_endure_origin, run_endure_chain
from .init import run_init


def resolve_entity_root() -> Path:
    """Return the default entity root from ~/.fcp/config.json."""
    entity_id = get_default_entity()
    if not entity_id:
        ui.print_err("No default entity set.")
        ui.print_err("Run 'fcp init' to create one, or 'fcp set <entity_id>' to select one.")
        sys.exit(1)
    root = entity_root_for(entity_id)
    if not (root / ".fcp-entity").exists():
        ui.print_err(f"Entity '{entity_id}' not found at {root}")
        ui.print_err("Run 'fcp init' to create it, or 'fcp set <entity_id>' to select another.")
        sys.exit(1)
    return root


def print_help() -> None:
    print("""
  fcp                              — boot default entity (workspace_focus = cwd)
  fcp init                         — create or update an entity
  fcp list                         — list installed entities
  fcp set <entity_id>              — set default entity
  fcp status                       — entity status overview (no session needed)
  fcp agenda                       — list scheduled tasks (no session needed)
  fcp model                        — interactive model picker
  fcp endure sync                  — sync entity root with git remote
  fcp endure origin                — set or update git remote origin
  fcp endure chain                 — display integrity chain
  fcp decommission --archive       — archive entity (reversible)
  fcp decommission --destroy       — destroy entity permanently
  fcp doctor [--fix]               — check integrity; --fix to repair
  fcp --auto <cron_id>             — run scheduled task autonomously in auto:session
  fcp --verbose                    — boot entity with verbose mode enabled
  fcp --debugger[=all|chat|boot]   — boot entity with debugger mode enabled
  fcp update [--dry-run]           — update FCP from the main repository

  fcp help                         — this message
""")


def main() -> None:
    try:
        _main()
    except KeyboardInterrupt:
        print("\n[interrupted]")
        sys.exit(0)


def _main() -> None:
    load_env_file()
    args = sys.argv[1:]
    cwd = Path.cwd()

    verbose = "--verbose" in args

    _dbg_mode: str | None = None
    _clean: list[str] = []
    _skip_next = False
    for i, a in enumerate(args):
        if _skip_next:
            _skip_next = False
            continue
        if a.startswith("--debugger="):
            _dbg_mode = a.split("=", 1)[1] or "all"
        elif a == "--debugger":
            nxt = args[i + 1] if i + 1 < len(args) else ""
            if nxt in ("all", "chat", "boot"):
                _dbg_mode = nxt
                _skip_next = True
            else:
                _dbg_mode = "all"
        elif a != "--verbose":
            _clean.append(a)
    args = _clean

    if not args:
        from ..operator import set_verbose, set_debugger
        entity_root = resolve_entity_root()
        if verbose and not _dbg_mode:
            set_verbose(True)
        if _dbg_mode:
            set_debugger(_dbg_mode)
        run_normal(Layout(entity_root), workspace_focus=cwd)
        return

    cmd = args[0]
    rest = args[1:]

    if cmd in ("help", "--help", "-h"):
        print_help()
        return

    if cmd == "init":
        fcp_ref_root = Path(__file__).parent.parent.parent
        run_init(fcp_ref_root)
        return

    if cmd == "list":
        entities = list_entities()
        default = get_default_entity()
        if not entities:
            print("  No entities installed. Run 'fcp init' to create one.")
            return
        print()
        for eid in entities:
            marker = "  ← default" if eid == default else ""
            print(f"  {eid}{marker}")
        print()
        return

    if cmd == "set" and rest:
        entity_id = rest[0]
        root = entity_root_for(entity_id)
        if not (root / ".fcp-entity").exists():
            ui.print_err(f"Entity '{entity_id}' not found at {root}")
            sys.exit(1)
        set_default_entity(entity_id)
        ui.print_ok(f"Default entity set to '{entity_id}'")
        return

    entity_root = resolve_entity_root()

    if cmd == "status":
        run_status(Layout(entity_root))
        return

    if cmd == "agenda":
        run_agenda(Layout(entity_root))
        return

    if cmd == "doctor":
        run_doctor(Layout(entity_root), rest)
        return

    if cmd == "decommission":
        run_decommission(Layout(entity_root), rest)
        return

    if cmd == "model":
        run_model(Layout(entity_root))
        return

    if cmd == "endure" and rest:
        sub = rest[0]
        if sub == "sync":
            run_endure_sync(Layout(entity_root))
        elif sub == "origin":
            run_endure_origin(Layout(entity_root))
        elif sub == "chain":
            run_endure_chain(Layout(entity_root))
        else:
            ui.print_err(f"Unknown endure subcommand: {sub}")
            print("  usage: fcp endure sync | origin | chain")
            sys.exit(1)
        return

    if cmd == "--auto" and rest:
        run_auto(Layout(entity_root), rest[0])
        return

    if cmd in ("update", "upgrade"):
        run_update(dry_run="--dry-run" in rest)
        return

    print(f"unknown command: {cmd}")
    print("usage: fcp [init | list | set <id> | status | agenda | model | update | doctor [--fix] | decommission --archive|--destroy | endure sync | --auto <cron_id>]")
    sys.exit(1)
