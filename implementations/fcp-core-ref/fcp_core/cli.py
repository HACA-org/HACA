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

    # --debugger[=mode] or --debugger <mode>
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
            # peek at next arg for optional mode
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
        # normal boot + session
        from .store import Layout
        from .operator import set_verbose, set_debugger
        if verbose and not _dbg_mode:
            set_verbose(True)
        if _dbg_mode:
            set_debugger(_dbg_mode)
        _run_normal(Layout(entity_root))
        return

    cmd = args[0]
    rest = args[1:]

    if cmd in ("help", "--help", "-h"):
        _print_help()
        return

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

    if cmd == "model":
        from .store import Layout
        _run_model(Layout(entity_root))
        return

    if cmd == "--auto" and rest:
        from .store import Layout
        _run_auto(Layout(entity_root), rest[0])
        return

    print(f"unknown command: {cmd}")
    print("usage: ./fcp-core [init | model | doctor [--fix] | decommission --archive|--destroy | --auto <cron_id>]")
    sys.exit(1)


def _print_help() -> None:
    print("""
  ./fcp-core                         — boot entity and start session
  ./fcp-core init                    — initialize a new entity
  ./fcp-core model                   — interactive model picker
  ./fcp-core doctor [--fix]          — check integrity; --fix to repair
  ./fcp-core decommission --archive  — archive entity (reversible)
  ./fcp-core decommission --destroy  — destroy entity permanently
  ./fcp-core --auto <cron_id>        — run scheduled task autonomously
  ./fcp-core --verbose               — boot with verbose mode enabled
  ./fcp-core --debugger[=all|chat|boot]
                                     — boot with debugger mode enabled
  ./fcp-core help | --help | -h      — this message
""")


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

    _load_env_file()

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

    _print_boot_header(layout, index)

    # Present any pending evolution proposals before starting the session.
    # Operator must approve or reject all of them before proceeding.
    while present_evolution_proposals(layout):
        pass

    while True:
        close_reason = run_session(layout, adapter, index)

        present_evolution_proposals(layout)

        from .hooks import run_hook
        run_hook(layout, "on_session_close", {"close_reason": close_reason})

        print("[FCP-Core] Running Sleep Cycle...")
        try:
            run_sleep_cycle(layout)
        except Exception as exc:
            print(f"[SLEEP CYCLE ERROR] {exc}")

        if close_reason not in ("operator_reset", "endure_approved"):
            break

        if close_reason == "endure_approved":
            print("[FCP-Core] Evolution approved. Rebooting...")
        else:
            print("[FCP-Core] Starting new session...")
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
# Auto session — triggered by host cron
# ---------------------------------------------------------------------------

def _run_auto(layout: "Layout", cron_id: str) -> None:
    """Execute a scheduled task autonomously, without an Operator session."""
    import json
    from .boot import run as boot_run, BootError
    from .cpe.base import make_adapter
    from .fap import FAPError
    from .sleep import run_sleep_cycle
    from .store import read_json
    from .sil import write_notification

    # Load agenda and find task
    if not layout.agenda.exists():
        print(f"[FCP-Auto] agenda not found — no task to run")
        sys.exit(1)
    try:
        agenda = json.loads(layout.agenda.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[FCP-Auto] could not read agenda: {exc}")
        sys.exit(1)
    task = next((t for t in agenda.get("tasks", []) if t.get("id") == cron_id), None)
    if task is None:
        print(f"[FCP-Auto] task not found: {cron_id}")
        sys.exit(1)
    if task.get("status") != "approved":
        print(f"[FCP-Auto] task not approved: {cron_id} (status: {task.get('status')})")
        sys.exit(1)

    executor = task.get("executor", "cpe")
    wake_up_message = task.get("wake_up_message", "")
    description = task.get("description", cron_id)

    print(f"[FCP-Auto] starting — {description} ({executor})")

    # executor: worker — invoke worker_skill directly, no session needed
    if executor == "worker":
        _run_auto_worker(layout, task, wake_up_message)
        return

    # executor: cpe — full auto_session
    try:
        boot_run(layout)
    except FAPError as exc:
        print(f"[FAP FAILED] {exc}")
        sys.exit(1)
    except BootError as exc:
        print(f"[BOOT FAILED] {exc}")
        sys.exit(1)

    _load_env_file()

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

    # Inject wake_up as first stimulus via first-stimuli.json
    from .store import atomic_write
    atomic_write(layout.first_stimuli, {"message": wake_up_message, "source": "cron", "cron_id": cron_id})

    from .session import run_session
    run_session(layout, adapter, index)

    try:
        run_sleep_cycle(layout)
    except Exception as exc:
        print(f"[SLEEP CYCLE ERROR] {exc}")

    # Update last_run in agenda
    import datetime as _dt
    task["last_run"] = _dt.datetime.utcnow().isoformat() + "Z"
    atomic_write(layout.agenda, agenda)

    write_notification(layout, "auto_session_complete", {
        "cron_id": cron_id,
        "description": description,
        "last_run": task["last_run"],
    })
    print(f"[FCP-Auto] complete — {cron_id}")


def _run_auto_worker(layout: "Layout", task: dict, wake_up_message: str) -> None:
    """Run a worker_skill task directly without a CPE session."""
    import datetime as _dt
    import json
    from .store import atomic_write, read_json
    from .sil import write_notification
    from .exec_ import dispatch

    _load_env_file()

    index: dict = {}
    if layout.skills_index.exists():
        index = read_json(layout.skills_index)

    cron_id = task.get("id", "")
    description = task.get("description", cron_id)

    try:
        result = dispatch(layout, "worker_skill", {
            "task": wake_up_message,
            "context": task.get("task", ""),
            "persona": "FCP autonomous worker",
        }, index)
    except Exception as exc:
        result = f"error: {exc}"

    now = _dt.datetime.utcnow().isoformat() + "Z"

    # Update last_run
    if layout.agenda.exists():
        try:
            agenda = json.loads(layout.agenda.read_text(encoding="utf-8"))
            for t in agenda.get("tasks", []):
                if t.get("id") == cron_id:
                    t["last_run"] = now
            atomic_write(layout.agenda, agenda)
        except Exception:
            pass

    write_notification(layout, "auto_worker_complete", {
        "cron_id": cron_id,
        "description": description,
        "result": result,
        "last_run": now,
    })
    print(f"[FCP-Auto] worker complete — {cron_id}")


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
# Model — select provider/model and update API key outside of a session
# ---------------------------------------------------------------------------

def _run_model(layout: "Layout") -> None:
    import os
    from .cpe.base import BACKENDS, KNOWN_MODELS, fetch_ollama_models
    from .store import read_json, atomic_write

    try:
        baseline = read_json(layout.baseline)
    except Exception:
        print("[ERROR] Could not read baseline.json — run ./fcp-core init first.")
        sys.exit(1)

    cpe_cfg = baseline.get("cpe", {})
    current_backend = cpe_cfg.get("backend", "ollama")
    current_model = cpe_cfg.get("model", "")

    # Build flat list of "backend:model" labels
    items: list[str] = []
    pairs: list[tuple[str, str]] = []  # (backend, model) parallel to items

    for backend in BACKENDS:
        models = fetch_ollama_models() if backend == "ollama" else KNOWN_MODELS.get(backend, [])
        for m in models:
            active = backend == current_backend and m == current_model
            label = f"\x1b[1;96m{backend}:{m} ✓\x1b[0m" if active else f"{backend}:{m}"
            items.append(label)
            pairs.append((backend, m))

    if not items:
        print("[ERROR] No models available.")
        sys.exit(1)

    default_idx = next(
        (i for i, (b, m) in enumerate(pairs) if b == current_backend and m == current_model),
        0,
    )
    chosen_label = _pick_from_list("Select provider and model", items, default_idx)
    # find the pair that matches the chosen label (strip marker)
    chosen_idx = next(i for i, lbl in enumerate(items) if lbl == chosen_label)
    backend, model = pairs[chosen_idx]

    # API key (skip for ollama)
    if backend != "ollama":
        env_var = _API_KEY_ENV.get(backend, "")
        if env_var:
            current_key_hint = "set" if os.environ.get(env_var) else "not set"
            try:
                api_key = input(f"{env_var} [{current_key_hint}] (leave blank to keep): ").strip()
            except EOFError:
                api_key = ""
            if api_key:
                _save_api_key(layout.root.name, env_var, api_key)
                _load_env_file()

    cpe_cfg["backend"] = backend
    cpe_cfg["model"] = model
    baseline["cpe"] = cpe_cfg
    atomic_write(layout.baseline, baseline)
    print(f"[FCP-Core] Model set to {backend}:{model}")


# ---------------------------------------------------------------------------
# Init helpers
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------

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


def _load_env_file() -> None:
    """Load KEY=value pairs from ~/.fcp-core.env into os.environ (no-op if absent)."""
    import os
    env_file = Path.home() / ".fcp-core.env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = val.strip()


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

    from .cpe.base import BACKENDS, KNOWN_MODELS, fetch_ollama_models
    backend = _pick_from_list("CPE backend", BACKENDS)

    if backend == "ollama":
        ollama_models = fetch_ollama_models()
        if ollama_models:
            model = _pick_from_list("Model", ollama_models)
        else:
            model = input("Model (default: llama3.2): ").strip() or "llama3.2"
    else:
        model_list = KNOWN_MODELS[backend]
        model = _pick_from_list("Model", model_list)

        env_var = _API_KEY_ENV[backend]
        try:
            api_key = input(f"{env_var}: ").strip()
        except EOFError:
            api_key = ""
        if api_key:
            _save_api_key(entity_root.name, env_var, api_key)

    from .store import atomic_write
    atomic_write(entity_root / "state" / "baseline.json", {
        "version": "1.0.0",
        "entity_id": entity_root.name,
        "cpe": {"backend": backend, "model": model, "topology": "transparent"},
        "context_window": {"budget_tokens": 200000, "critical_pct": 80},
        "drift": {"comparison_mechanism": "hash", "threshold": 0.0},
        "session_store": {"rotation_threshold_bytes": 1000000},
        "working_memory": {"max_entries": 50},
        "heartbeat": {"interval_seconds": 30, "cycle_threshold": 10},
        "watchdog": {"sil_threshold_seconds": 25},
        "fault": {"n_retry": 3, "n_boot": 3, "n_channel": 3, "max_cycles": 50},
        "integrity_chain": {"checkpoint_interval": 10},
        "pre_session_buffer": {"max_entries": 20},
        "operator_channel": {"notifications_dir": "state/operator_notifications"},
    })

    atomic_write(entity_root / "state" / "integrity.json", {
        "version": "1.0", "algorithm": "sha256",
        "last_checkpoint": None, "files": {},
    })

    for p in [
        entity_root / "state" / "integrity_chain.jsonl",
        entity_root / "state" / "integrity.log",
        entity_root / "memory" / "session.jsonl",
    ]:
        p.write_text("", encoding="utf-8")

    atomic_write(entity_root / "memory" / "working-memory.json", {"entries": []})

    print(f"\n[FCP-Core] Initialised: {entity_root}")
    print("  First boot will run FAP (First Activation Protocol).")
    print("  Run: ./fcp-core")


_WIDTH = 50
_RESET = "\x1b[0m"
_DIM = "\x1b[2m"


def _print_block(label: str, lines: list, color: str = "\x1b[96m") -> None:
    """Print a bordered block with a colored header label and closing border."""
    border = "─" * (_WIDTH - len(label) - 3)
    print(f"{color}╭─ {label} {border}╮{_RESET}")
    for line in lines:
        print(f"{_DIM}│{_RESET} {line}")
    print(f"{color}╰{'─' * _WIDTH}╯{_RESET}")


def _print_boot_header(layout: "Layout", index: dict) -> None:
    from .session import build_boot_context, build_boot_stats, _tool_declarations
    from .store import read_json

    system, chat_history = build_boot_context(layout, index)
    tools = _tool_declarations(layout, index)
    s = build_boot_stats(layout, index, system, chat_history, tools)

    ctx_str = f"{s['ctx_pct']}%" if s["ctx_pct"] is not None else "?%"
    evol_str = f"{s['evolutions_auth']}/{s['evolutions_total']}"

    try:
        baseline = read_json(layout.baseline)
        cpe_cfg = baseline.get("cpe", {})
        model_str = f"{cpe_cfg.get('backend', '?')}:{cpe_cfg.get('model', '?')}"
    except Exception:
        model_str = "?"

    header_lines = [
        f"{model_str} | tools: {s['tools']}",
        f"boot: {ctx_str} ctx | sessions: {s['sessions']} | cycles: {s['cycles']}",
        f"memories: {s['memories']} | evolutions: {evol_str} | skills: {s['skills']}",
    ]
    _print_block("FCP-Core", header_lines, color="\x1b[90m")  # dark gray
    notif_str = f" You have {s['notifications']} new notifications in /inbox." if s["notifications"] else ""
    print(f"Type your message or /help.{notif_str}")


