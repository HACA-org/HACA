"""
CLI entry point — FCP-Core §12.1.

Usage (always run from inside the entity root):
  ./fcp-core                          — boot and run a session
  ./fcp-core init                     — initialise entity root in cwd
  ./fcp-core doctor [--fix]           — check/repair without booting
  ./fcp-core decommission --archive | --destroy
"""

from __future__ import annotations

import itertools
import sys
from pathlib import Path


def main() -> None:
    try:
        _main()
    except KeyboardInterrupt:
        print("\n[interrupted]")
        sys.exit(0)


def _main() -> None:
    args = sys.argv[1:]
    entity_root = Path.cwd()

    verbose = "--verbose" in args
    args = [a for a in args if a != "--verbose"]

    if not args:
        # normal boot + session
        from .store import Layout
        if verbose:
            from .operator import set_verbose
            set_verbose(True)
        _run_normal(Layout(entity_root))
        return

    cmd = args[0]
    rest = args[1:]

    if cmd == "init":
        _run_init(entity_root)
        return

    if cmd == "doctor":
        from .store import Layout
        _run_doctor(Layout(entity_root), rest)
        return

    if cmd == "decommission":
        from .store import Layout
        _run_decommission(Layout(entity_root), rest)
        return

    print(f"unknown command: {cmd}")
    print("usage: ./fcp-core [init | doctor [--fix] | decommission --archive|--destroy]")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Normal boot + session loop
# ---------------------------------------------------------------------------

def _run_normal(layout: "Layout") -> None:
    from .boot import run as boot_run, BootError
    from .cpe.base import make_adapter
    from .fap import FAPError
    from .operator import (
        handle_platform_command,
        present_notifications,
        present_evolution_proposals,
    )
    from .session import run_session
    from .sleep import run_sleep_cycle
    from .store import read_json

    try:
        boot_result = boot_run(layout)
    except FAPError as exc:
        print(f"[FAP FAILED] {exc}")
        sys.exit(1)
    except BootError as exc:
        print(f"[BOOT FAILED] {exc}")
        sys.exit(1)

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

    index: dict = {}
    if layout.skills_index.exists():
        index = read_json(layout.skills_index)

    present_notifications(layout)
    print("[FCP-Core] Entity ready. Type your message or /help.")

    while True:
        close_reason = run_session(layout, adapter, index, greeting=True)

        present_evolution_proposals(layout)

        from .hooks import run_hook
        run_hook(layout, "on_session_close", {"close_reason": close_reason})

        print("[FCP-Core] Running Sleep Cycle...")
        try:
            run_sleep_cycle(layout)
        except Exception as exc:
            print(f"[SLEEP CYCLE ERROR] {exc}")

        if close_reason != "operator_reset":
            break

        print("[FCP-Core] Starting new session...")
        # Clear session store for a clean context
        if layout.session_store.exists():
            layout.session_store.write_text("", encoding="utf-8")
        # Re-run boot for fresh context
        try:
            boot_run(layout)
        except (FAPError, BootError) as exc:
            print(f"[BOOT FAILED] {exc}")
            break
        index = {}
        if layout.skills_index.exists():
            index = read_json(layout.skills_index)

    print("[FCP-Core] Session complete.")


# ---------------------------------------------------------------------------
# Doctor — operates without booting
# ---------------------------------------------------------------------------

def _run_doctor(layout: "Layout", args: list[str]) -> None:
    from .compliance import run_all, print_report
    from .operator import fix_integrity_hashes
    from .sil import clear_beacon, beacon_is_active

    fix = "--fix" in args

    if fix:
        # Clear distress beacon if active
        if beacon_is_active(layout):
            clear_beacon(layout)
            print("  distress beacon cleared")

        # Remove stale session token
        if layout.session_token.exists():
            layout.session_token.unlink()
            print("  stale session token removed")

        # Repair volatile dirs
        for d in layout.volatile_dirs():
            if not d.exists():
                d.mkdir(parents=True, exist_ok=True)
                print(f"  created: {d.relative_to(layout.root)}")

        # Recalculate integrity hashes
        fix_integrity_hashes(layout)

    findings = run_all(layout)
    print_report(findings)

    failed = [f for f in findings if not f.passed]
    if failed:
        print(f"\n  {len(failed)} issue(s) found. Run ./fcp-core doctor --fix to repair.")


# ---------------------------------------------------------------------------
# Decommission
# ---------------------------------------------------------------------------

def _run_decommission(layout: "Layout", args: list[str]) -> None:
    from .boot import run as boot_run, BootError
    from .cpe.base import make_adapter
    from .fap import FAPError
    from .acp import make as acp_make
    from .operator import present_evolution_proposals
    from .session import run_session
    from .sleep import run_sleep_cycle
    from .store import read_json
    from . import decommission as _decom

    do_archive = "--archive" in args
    do_destroy = "--destroy" in args

    if not do_archive and not do_destroy:
        print("decommission requires --archive or --destroy")
        sys.exit(1)

    mode = "archive" if do_archive else "destroy"

    # Check for partial decommission
    partial = _decom.detect_partial(layout)
    if partial:
        print(f"[FCP-Core] Partial decommission detected (phase: {partial.get('phase')}, mode: {partial.get('mode')}).")
        answer = input("Resume? [yes/no] ").strip().lower()
        if answer != "yes":
            print("Aborted.")
            sys.exit(0)
        mode = partial.get("mode", mode)
        # Resume from where it stopped — skip boot and session
        def _sleep_fn() -> None:
            present_evolution_proposals(layout)
            run_sleep_cycle(layout)
        _decom.run(layout, mode, _sleep_fn, partial=partial)
        return

    # --destroy requires explicit confirmation
    if do_destroy:
        print(f"[FCP-Core] WARNING: This will permanently destroy the entity at {layout.root}.")
        answer = input("Type 'yes' to confirm destruction: ").strip().lower()
        if answer != "yes":
            print("Aborted.")
            sys.exit(0)

    try:
        boot_run(layout)
    except FAPError as exc:
        print(f"[FAP FAILED] {exc}")
        sys.exit(1)
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
        data={"type": "DECOMMISSION", "mode": mode},
    )
    run_session(layout, adapter, index, inject=[envelope])

    def _sleep_fn() -> None:
        present_evolution_proposals(layout)
        run_sleep_cycle(layout)

    _decom.run(layout, mode, _sleep_fn)


# ---------------------------------------------------------------------------
# Init helpers
# ---------------------------------------------------------------------------

def _fetch_ollama_models() -> list[str]:
    """Return list of model names from the local Ollama instance. Empty on failure."""
    try:
        import urllib.request, json as _json
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3) as resp:
            data = _json.loads(resp.read().decode())
        return [m["name"] for m in data.get("models", [])]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------

_BACKEND_MODELS: dict[str, list[str]] = {
    "ollama": [],  # populated dynamically
    "anthropic": [
        "claude-opus-4-6",
        "claude-sonnet-4-6",
        "claude-haiku-4-5-20251001",
    ],
    "openai": [
        "gpt-4o",
        "gpt-4o-mini",
        "o3-mini",
    ],
    "google": [
        "gemini-3.1-flash-lite-preview",
        "gemini-3-flash-preview",
        "gemini-3.1-pro-preview",
        "gemini-2.5-flash",
        "gemini-2.0-flash",
    ],
}

_BACKENDS = ["ollama", "anthropic", "openai", "google"]

_API_KEY_ENV: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "google": "GOOGLE_API_KEY",
}


def _pick_from_list(prompt: str, items: list[str], default_idx: int = 0) -> str:
    """Generic interactive arrow-key picker. Falls back to text input on error."""
    import tty, termios

    if not items:
        return input(f"{prompt}: ").strip()

    selected = default_idx
    first_render = True

    def _render(idx: int) -> None:
        nonlocal first_render
        if not first_render:
            sys.stdout.write(f"\033[{len(items)}A")
        first_render = False
        for i, name in enumerate(items):
            prefix = " > " if i == idx else "   "
            sys.stdout.write(f"\r{prefix}{name}\033[K\n")
        sys.stdout.flush()

    print(f"{prompt} (↑↓ to move, Enter to confirm):")
    _render(selected)

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        while True:
            ch = sys.stdin.read(1)
            if ch in ("\r", "\n"):
                break
            if ch == "\x03":
                raise KeyboardInterrupt
            if ch == "\x1b":
                ch2 = sys.stdin.read(1)
                ch3 = sys.stdin.read(1)
                if ch2 == "[":
                    if ch3 == "A" and selected > 0:
                        selected -= 1
                    elif ch3 == "B" and selected < len(items) - 1:
                        selected += 1
            _render(selected)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)

    print()
    return items[selected]


def _save_api_key(entity_name: str, env_var: str, api_key: str) -> None:
    """Append or update KEY=value in ~/.fcp-core.env."""
    import os
    env_file = Path.home() / ".fcp-core.env"
    lines: list[str] = []
    if env_file.exists():
        lines = env_file.read_text(encoding="utf-8").splitlines()

    prefix = f"{env_var}="
    updated = False
    for i, line in enumerate(lines):
        if line.startswith(prefix):
            lines[i] = f"{prefix}{api_key}"
            updated = True
            break
    if not updated:
        lines.append(f"{prefix}{api_key}")

    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.chmod(env_file, 0o600)
    print(f"  API key saved to {env_file} (export {env_var} or source it before running ./fcp-core)")


def _run_init(entity_root: Path) -> None:
    """Create runtime dirs inside entity_root (cwd).

    Structural content (boot.md, persona/, skills/, hooks/) must already exist
    in entity_root — they are committed to the repo and not generated here.
    workspace/ is never touched (operator may have projects there).
    """
    import shutil

    missing = []
    if not (entity_root / "boot.md").exists():
        missing.append("boot.md")
    if not (entity_root / "persona").is_dir() or not any((entity_root / "persona").iterdir()):
        missing.append("persona/ (must have at least one file)")
    if missing:
        print(f"[ERROR] Missing structural content: {', '.join(missing)}")
        print("  These files belong in the repo and must exist before running init.")
        sys.exit(1)

    if (entity_root / "state").exists() or (entity_root / "memory").exists():
        try:
            answer = input("Already initialised (state/ or memory/ exists). Re-initialise? [y/N] ").strip().lower()
        except EOFError:
            answer = "n"
        if answer != "y":
            sys.exit(0)
        for d in ["state", "memory", "io"]:
            p = entity_root / d
            if p.exists():
                shutil.rmtree(p)

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

    print("=== FCP-Core Init ===")

    backend = _pick_from_list("CPE backend", _BACKENDS)

    if backend == "ollama":
        ollama_models = _fetch_ollama_models()
        if ollama_models:
            model = _pick_from_list("Model", ollama_models)
        else:
            model = input("Model (default: llama3.2): ").strip() or "llama3.2"
    else:
        model_list = _BACKEND_MODELS[backend]
        model = _pick_from_list("Model", model_list)

        env_var = _API_KEY_ENV[backend]
        try:
            api_key = input(f"{env_var}: ").strip()
        except EOFError:
            api_key = ""
        if api_key:
            _save_api_key(entity_root.name, env_var, api_key)

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

    _atomic_write(entity_root / "state" / "integrity.json", {
        "version": "1.0", "algorithm": "sha256",
        "genesis_omega": None, "last_checkpoint": None, "files": {},
    })

    for p in [
        entity_root / "state" / "integrity_chain.jsonl",
        entity_root / "state" / "integrity.log",
        entity_root / "memory" / "session.jsonl",
    ]:
        p.write_text("", encoding="utf-8")

    _atomic_write(entity_root / "memory" / "working-memory.json", {"entries": []})

    print(f"\n[FCP-Core] Initialised: {entity_root}")
    print("  First boot will run FAP (First Activation Protocol).")
    print("  Run: ./fcp-core")


def _atomic_write(path: Path, data: object) -> None:
    import json
    import os
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)
