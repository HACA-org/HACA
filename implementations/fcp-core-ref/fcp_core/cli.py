"""
CLI entry point — FCP-Core §12.1.

Usage:
  fcp-core init <entity-root>                    — create a new entity root skeleton
  fcp-core <entity-root>                         — boot and run a session
  fcp-core <entity-root> --notifications         — print pending notifications and exit
  fcp-core <entity-root> decommission --archive | --destroy
"""

from __future__ import annotations

import itertools
import sys
from pathlib import Path


def main() -> None:
    args = sys.argv[1:]
    if not args:
        print("usage: fcp-core init <entity-root> | fcp-core <entity-root> [--notifications] [decommission --archive|--destroy]")
        sys.exit(1)

    # init subcommand — no entity root required to exist yet
    if args[0] == "init":
        if len(args) < 2:
            print("usage: fcp-core init <entity-root>")
            sys.exit(1)
        _run_init(Path(args[1]).resolve())
        return

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
    from .boot import run as boot_run, BootError
    from .cpe.base import make_adapter
    from .operator import (
        handle_platform_command,
        present_notifications,
        present_evolution_proposals,
    )
    from .session import run_session
    from .sleep import run_sleep_cycle
    from .store import read_json

    # Boot
    try:
        boot_result = boot_run(layout)
    except BootError as exc:
        print(f"[BOOT FAILED] {exc}")
        sys.exit(1)

    # Adapter from baseline
    try:
        baseline = read_json(layout.baseline)
        cpe_cfg = baseline.get("cpe", {})
        adapter = make_adapter(
            backend=cpe_cfg.get("backend", "ollama"),
            model=cpe_cfg.get("model", ""),
            api_key="",
        )
    except Exception as exc:
        print(f"[CPE ERROR] {exc}")
        sys.exit(1)

    # Load sealed skill index
    index: dict = {}
    if layout.skills_index.exists():
        index = read_json(layout.skills_index)

    # Present pending notifications
    present_notifications(layout)

    print("[FCP-Core] Entity ready. Type your message or /help.")

    # Session loop — each user message triggers one cognitive cycle
    while True:
        try:
            user_input = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not user_input:
            continue

        # platform commands
        if user_input.startswith("/"):
            if handle_platform_command(layout, user_input):
                continue
            from .operator import resolve_alias
            from .exec_ import dispatch, SkillRejected
            skill_name = resolve_alias(layout, user_input)
            if skill_name:
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
        from .acp import make as acp_make
        from .store import append_jsonl
        envelope = acp_make(env_type="MSG", source="operator", data=user_input)
        append_jsonl(layout.session_store, envelope)

        close_reason = run_session(layout, adapter, index)
        if close_reason == "session_close":
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
    from .boot import run as boot_run, BootError
    from .cpe.base import make_adapter
    from .acp import make as acp_make
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
        boot_result = boot_run(layout)
    except BootError as exc:
        print(f"[BOOT FAILED] {exc}")
        sys.exit(1)

    baseline = read_json(layout.baseline)
    cpe_cfg = baseline.get("cpe", {})
    adapter = make_adapter(
        backend=cpe_cfg.get("backend", "ollama"),
        model=cpe_cfg.get("model", ""),
        api_key="",
    )
    index: dict = {}
    if layout.skills_index.exists():
        index = read_json(layout.skills_index)

    envelope = acp_make(
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


# ---------------------------------------------------------------------------
# Init — create a new entity root skeleton
# ---------------------------------------------------------------------------

def _run_init(entity_root: Path) -> None:
    """Create runtime dirs (memory/, state/, io/, workspace/) inside entity_root.

    Structural content (boot.md, persona/, skills/, hooks/) must already exist
    in entity_root — they are committed to the repo and not generated here.
    """
    import os

    # Validate structural prerequisites
    missing = []
    if not (entity_root / "boot.md").exists():
        missing.append("boot.md")
    if not (entity_root / "persona").is_dir() or not any((entity_root / "persona").iterdir()):
        missing.append("persona/ (must have at least one file)")
    if missing:
        print(f"[ERROR] Missing structural content in {entity_root}: {', '.join(missing)}")
        print("  These files belong in the repo and must exist before running init.")
        sys.exit(1)

    # Check nothing was already initialised
    if (entity_root / "state").exists() or (entity_root / "memory").exists():
        print(f"[ERROR] {entity_root} appears already initialised (state/ or memory/ exists).")
        print("  Remove those directories manually if you want to re-initialise.")
        sys.exit(1)

    # Runtime directories
    runtime_dirs = [
        entity_root / "memory" / "episodic",
        entity_root / "memory" / "semantic",
        entity_root / "memory" / "active_context",
        entity_root / "state" / "sentinels",
        entity_root / "state" / "snapshots",
        entity_root / "state" / "operator_notifications",
        entity_root / "io" / "inbox" / "presession",
        entity_root / "io" / "spool",
        entity_root / "workspace" / "stage",
    ]
    for d in runtime_dirs:
        d.mkdir(parents=True, exist_ok=True)

    # baseline — ask for backend/model
    print("=== FCP-Core Init ===")
    backend = input("CPE backend [ollama/anthropic/openai/google] (default: ollama): ").strip() or "ollama"
    model_defaults = {
        "ollama": "llama3.2",
        "anthropic": "claude-sonnet-4-6",
        "openai": "gpt-4o",
        "google": "gemini-2.0-flash",
    }
    default_model = model_defaults.get(backend, "")
    model = input(f"Model (default: {default_model}): ").strip() or default_model

    _atomic_write(entity_root / "state" / "baseline.json", {
        "version": "1.0.0",
        "entity_id": entity_root.name,
        "profile": "HACA-Core",
        "cpe": {"backend": backend, "model": model, "topology": "transparent"},
        "context_window": {"budget_tokens": 200000, "critical_pct": 80},
        "drift": {"comparison_mechanism": "hash", "threshold": 0.0},
        "session_store": {"rotation_threshold_bytes": 1000000},
        "working_memory": {"max_entries": 50},
        "heartbeat": {"interval_seconds": 30, "cycle_threshold": 10},
        "watchdog": {"sil_threshold_seconds": 25},
        "fault": {"n_retry": 3, "n_boot": 3, "n_channel": 3},
        "integrity_chain": {"checkpoint_interval": 10},
        "pre_session_buffer": {"max_entries": 20},
        "operator_channel": {"notifications_dir": "state/operator_notifications"},
    })

    # integrity doc (empty — FAP will populate)
    _atomic_write(entity_root / "state" / "integrity.json", {
        "version": "1.0", "algorithm": "sha256",
        "genesis_omega": None, "last_checkpoint": None, "files": {},
    })

    # empty runtime files
    for p in [
        entity_root / "state" / "integrity_chain.jsonl",
        entity_root / "state" / "integrity.log",
        entity_root / "memory" / "session.jsonl",
    ]:
        p.write_text("", encoding="utf-8")

    _atomic_write(entity_root / "memory" / "working-memory.json", {"entries": []})

    print(f"\n[FCP-Core] Initialised: {entity_root}")
    print("  First boot will run FAP (First Activation Protocol).")
    print(f"  Run: ./fcp-core {entity_root}")


def _atomic_write(path: Path, data: object) -> None:
    import json
    import os
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)
