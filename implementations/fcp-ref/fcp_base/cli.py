"""
CLI entry point — FCP §12.1.

Usage (always run from inside the entity root):
  ./fcp                          — boot and run a session
  ./fcp init                     — initialise entity root in cwd
  ./fcp doctor [--fix]           — check/repair without booting
  ./fcp decommission --archive | --destroy
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
        # fcp_ref_root is two levels up from this file: fcp_base/ -> fcp-ref/
        fcp_ref_root = Path(__file__).parent.parent
        _run_init(fcp_ref_root)
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
    print("usage: ./fcp [init | model | doctor [--fix] | decommission --archive|--destroy | --auto <cron_id>]")
    sys.exit(1)


def _print_help() -> None:
    print("""
  ./fcp                         — boot entity and start session
  ./fcp init                    — initialize a new entity
  ./fcp model                   — interactive model picker
  ./fcp doctor [--fix]          — check integrity; --fix to repair
  ./fcp decommission --archive  — archive entity (reversible)
  ./fcp decommission --destroy  — destroy entity permanently
  ./fcp --auto <cron_id>        — run scheduled task autonomously
  ./fcp --verbose               — boot with verbose mode enabled
  ./fcp --debugger[=all|chat|boot]
                                — boot with debugger mode enabled
  ./fcp help | --help | -h      — this message
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

        print("[FCP] Running Sleep Cycle...")
        try:
            run_sleep_cycle(layout)
        except Exception as exc:
            print(f"[SLEEP CYCLE ERROR] {exc}")

        if close_reason not in ("operator_reset", "endure_approved"):
            break

        if close_reason == "endure_approved":
            print("[FCP] Evolution approved. Rebooting...")
        else:
            print("[FCP] Starting new session...")
        # Re-run boot for fresh context
        try:
            boot_run(layout)
        except (FAPError, BootError) as exc:
            print(f"[BOOT FAILED] {exc}")
            break
        index = {}
        if layout.skills_index.exists():
            index = read_json(layout.skills_index)

    print("[FCP] Session complete.")


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
    from .stimuli import inject_wakeup
    inject_wakeup(layout, cron_id, wake_up_message)

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
        print(f"\n  {len(failed)} issue(s) found. Run ./fcp doctor --fix to repair.")


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
        print(f"[FCP] Partial decommission detected (phase: {partial.get('phase')}, mode: {partial.get('mode')}).")
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
        print(f"[FCP] WARNING: This will permanently destroy the entity at {layout.root}.")
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
        print("[ERROR] Could not read baseline.json — run ./fcp init first.")
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
    print(f"[FCP] Model set to {backend}:{model}")


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


def _pick_from_list(prompt: str, items: list[str], default_idx: int = 0, indent: str = "") -> str:
    """Generic interactive arrow-key picker. Falls back to text input on error."""
    import tty, termios

    if not items:
        return input(f"{indent}{prompt}: ").strip()

    selected = default_idx
    first_render = True

    def _render(idx: int) -> None:
        nonlocal first_render
        if not first_render:
            sys.stdout.write(f"\033[{len(items)}A")
        first_render = False
        for i, name in enumerate(items):
            prefix = f"{indent} > " if i == idx else f"{indent}   "
            sys.stdout.write(f"\r{prefix}{name}\033[K\n")
        sys.stdout.flush()

    print(f"{indent}{prompt} (↑↓ to move, Enter to confirm):")
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
    """Load KEY=value pairs from ~/.fcp.env into os.environ (no-op if absent)."""
    import os
    env_file = Path.home() / ".fcp.env"
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
    """Append or update KEY=value in ~/.fcp.env."""
    import os
    env_file = Path.home() / ".fcp.env"
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
    print(f"  API key saved to {env_file} (export {env_var} or source it before running ./fcp)")


def _read_fcp_version(fcp_ref_root: Path) -> str:
    """Read FCP version from pyproject.toml in fcp_ref_root."""
    try:
        import re
        text = (fcp_ref_root / "pyproject.toml").read_text(encoding="utf-8")
        m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
        if m:
            return m.group(1)
    except Exception:
        pass
    return "unknown"


def _run_init(fcp_ref_root: Path) -> None:
    """Interactive init — creates a new entity root from fcp-ref templates."""
    import json
    import shutil

    W = 60

    def _hr(label: str = "") -> None:
        if label:
            pad = W - len(label) - 4
            print(f"\n  ── {label} {'─' * pad}")
        else:
            print(f"  {'─' * W}")

    def _ask(prompt: str, default: str = "") -> str:
        hint = f" [{default}]" if default else ""
        try:
            val = input(f"  {prompt}{hint}: ").strip()
        except EOFError:
            val = ""
        return val or default

    def _confirm(prompt: str, default: bool = False) -> bool:
        hint = "Y/n" if default else "y/N"
        try:
            val = input(f"  {prompt} [{hint}]: ").strip().lower()
        except EOFError:
            val = ""
        if not val:
            return default
        return val.startswith("y")

    fcp_version = _read_fcp_version(fcp_ref_root)

    # ── Header ──────────────────────────────────────────────────────────────
    print()
    print(f"  {'─' * W}")
    print(f"  FCP — Filesystem Cognitive Platform v{fcp_version}")
    print(f"  HACA — Host-Agnostic Cognitive Architecture v1.0")
    print(f"  {'─' * W}")
    print(f"  FCP is a reference implementation of HACA and may contain")
    print(f"  errors. HACA is an open architecture specification for")
    print(f"  persistent cognitive entities.")
    print()
    print(f"  Contributions are welcome. Report issues and security")
    print(f"  vulnerabilities at: https://github.com/HACA-org/HACA")
    print()
    print(f"  Do not use in production without a prior security review.")
    print(f"  {'─' * W}")
    print()
    if not _confirm("Continue?"):
        sys.exit(0)

    # ── Step 1: Destination ─────────────────────────────────────────────────
    _hr("1. Entity destination")
    print()
    print("  Where should the entity root be created?")
    print("  Leave blank to use the current directory.")
    print()
    dest_input = _ask("Path", str(Path.cwd()))
    entity_root = Path(dest_input).expanduser().resolve()

    _ENTITY_MARKERS = ["fcp_base", "boot.md", "state", "memory", "skills", "hooks", "workspace", "fcp"]
    existing_markers = [m for m in _ENTITY_MARKERS if (entity_root / m).exists()]
    is_operational = len(existing_markers) == len(_ENTITY_MARKERS)
    is_nonempty = len(existing_markers) > 0 or (entity_root.exists() and any(entity_root.iterdir()))

    if is_operational:
        print(f"\n  [!] An existing entity was found at {entity_root}.")
        print(f"      Re-initialising will reset state/, memory/ and io/ (back to FAP).")
        print(f"      fcp_base/, skills/, hooks/, boot.md and persona/ will be preserved.")
        if not _confirm("Re-initialise?"):
            sys.exit(0)
        for d in ["state", "memory", "io"]:
            p = entity_root / d
            if p.exists():
                shutil.rmtree(p)
    elif is_nonempty:
        print(f"\n  [!] {entity_root} is not empty but does not look like a complete entity.")
        missing = [m for m in _ENTITY_MARKERS if m not in existing_markers]
        print(f"      Missing: {', '.join(missing)}")
        print(f"      Continuing will write all entity files, overwriting any existing content.")
        if not _confirm("Continue anyway?"):
            sys.exit(0)

    # ── Step 2: Profile ─────────────────────────────────────────────────────
    _hr("2. Profile")
    print()
    print("  HACA-Core — Zero-autonomy")
    print("    Every structural change and evolution requires explicit Operator")
    print("    approval. Designed for enterprise and adversarial environments.")
    print()
    print("  HACA-Evolve — Supervised autonomy")
    print("    The entity acts and evolves independently within a declared scope,")
    print("    under Operator supervision. Designed for long-term assistants")
    print("    and companions.")
    print()
    profile_items = [
        "HACA-Core   — Zero-autonomy",
        "HACA-Evolve — Supervised autonomy",
    ]
    profile_choice = _pick_from_list("Profile", profile_items, default_idx=0, indent="  ")
    profile = "haca-core" if profile_items.index(profile_choice) == 0 else "haca-evolve"
    haca_profile = "HACA-Core-1.0.0" if profile == "haca-core" else "HACA-Evolve-1.0.0"

    # ── Step 3: Evolve scope (only for haca-evolve) ─────────────────────────
    evolve_scope: dict = {}
    if profile == "haca-evolve":
        _hr("3. Autonomous scope")
        print()
        print("  Define what this entity is authorised to do autonomously.")
        print("  These permissions can be revoked by re-initialising.")
        print()

        print("  [1] Autonomous structural evolution")
        print("      The entity may modify its own entity root freely, including")
        print("      its own code. WARNING: this grants unrestricted write access")
        print("      to the entire entity root.")
        allow_evolution = _confirm("      Authorise?")

        print()
        print("  [2] Autonomous skill creation and installation")
        print("      The entity may create and install new skills without approval.")
        print("      WARNING: skills run as Python code with full access to the")
        print("      entity root. Only enable if you trust the entity's judgment.")
        allow_skills = _confirm("      Authorise?")

        print()
        print("  [3] Cognitive Mesh Interface (CMI) access")
        print("      The entity may connect to other entities via CMI channels.")
        print("      WARNING: CMI allows the entity to send and receive messages")
        print("      from other entities. Ensure you trust the mesh you join.")
        print()
        cmi_items = [
            "none    — No CMI access",
            "private — Private channels only",
            "public  — Public channels only",
            "both    — Private and public channels",
        ]
        cmi_choice = _pick_from_list("CMI access", cmi_items, default_idx=0, indent="      ")
        cmi_scope = cmi_choice.split()[0]

        print()
        print("  [4] Operator memory")
        print("      The entity may save your preferences and information across")
        print("      sessions. The entity will NEVER share your secrets (API keys,")
        print("      tokens, passwords). NOTE: you are also responsible for not")
        print("      sharing secrets directly in conversation — the entity cannot")
        print("      protect what it never receives.")
        allow_memory = _confirm("      Authorise?")

        print()
        print("  [5] Scope renewal interval")
        print("      These authorisations will expire and the entity will pause")
        print("      until you renew them. Enter 0 to disable expiry.")
        while True:
            renewal_input = _ask("      Renewal interval in days", "30")
            try:
                renewal_days = int(renewal_input)
                if renewal_days >= 0:
                    break
            except ValueError:
                pass
            print("  [ERROR] Please enter a non-negative integer.")

        evolve_scope = {
            "autonomous_evolution": allow_evolution,
            "autonomous_skills": allow_skills,
            "cmi_access": cmi_scope,
            "operator_memory": allow_memory,
            "renewal_days": renewal_days,
        }

    # ── Step 4: Dependencies ─────────────────────────────────────────────────
    _hr("4. Dependencies")
    print()
    import sys as _sys
    py_ver = _sys.version_info
    py_ok = py_ver >= (3, 10)
    py_str = f"{py_ver.major}.{py_ver.minor}.{py_ver.micro}"
    print(f"  Required:")
    print(f"    python >= 3.10    {'✓ ' + py_str if py_ok else '✗ ' + py_str + ' — REQUIRED'}")
    if not py_ok:
        print("\n  [ERROR] Python 3.10 or higher is required.")
        sys.exit(1)
    print()
    print(f"  Optional (not yet available — coming in a future release):")
    print(f"    rich              — enhanced terminal formatting")
    print(f"    textual           — interactive TUI (web panel, session dashboard)")

    # ── Step 5: CPE backend and model ────────────────────────────────────────
    _hr("5. CPE backend and model")
    print()
    from .cpe.base import BACKENDS, KNOWN_MODELS, fetch_ollama_models
    backend = _pick_from_list("Backend", BACKENDS, indent="  ")

    api_key_saved: str | None = None
    if backend == "ollama":
        ollama_models = fetch_ollama_models()
        if ollama_models:
            model = _pick_from_list("Model", ollama_models, indent="  ")
        else:
            model = _ask("Model", "llama3.2")
    else:
        model_list = KNOWN_MODELS[backend]
        model = _pick_from_list("Model", model_list, indent="  ")
        env_var = _API_KEY_ENV[backend]
        try:
            api_key = input(f"  {env_var}: ").strip()
        except EOFError:
            api_key = ""
        if api_key:
            _save_api_key(entity_root.name, env_var, api_key)
            api_key_saved = env_var

    # ── Step 6: Copy snapshot and create runtime dirs ────────────────────────
    _hr("6. Creating entity")
    print()
    entity_root.mkdir(parents=True, exist_ok=True)

    profile_dir = fcp_ref_root / ("fcp-core" if profile == "haca-core" else "fcp-evolve")

    # Copy structural content
    for src, dst_name in [
        (fcp_ref_root / "fcp_base",  "fcp_base"),
        (fcp_ref_root / "skills",    "skills"),
        (fcp_ref_root / "hooks",     "hooks"),
        (fcp_ref_root / "boot.md",   "boot.md"),
        (profile_dir / "persona",    "persona"),
    ]:
        dst = entity_root / dst_name
        if src.is_dir():
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
        elif src.is_file():
            shutil.copy2(src, dst)

    # Copy fcp CLI entrypoint
    fcp_cli_src = fcp_ref_root / "fcp"
    if fcp_cli_src.exists():
        fcp_cli_dst = entity_root / "fcp"
        shutil.copy2(fcp_cli_src, fcp_cli_dst)
        fcp_cli_dst.chmod(0o755)

    # Runtime directories
    for d in [
        entity_root / "memory" / "episodic",
        entity_root / "memory" / "semantic",
        entity_root / "memory" / "active_context",
        entity_root / "state" / "sentinels",
        entity_root / "state" / "snapshots",
        entity_root / "state" / "operator_notifications",
        entity_root / "io" / "inbox" / "presession",
        entity_root / "io" / "spool",
        entity_root / "workspace" / "stage",
    ]:
        d.mkdir(parents=True, exist_ok=True)

    # Load profile defaults and fill in choices
    from .store import atomic_write, read_json
    defaults_path = profile_dir / "defaults" / "baseline.json"
    baseline = read_json(defaults_path) if defaults_path.exists() else {}
    baseline["entity_id"] = entity_root.name
    baseline["fcp_version"] = fcp_version
    baseline["haca_version"] = "HACA-Arch-1.0.0"
    baseline["haca_profile"] = haca_profile
    baseline["cpe"] = {"backend": backend, "model": model, "topology": "transparent"}
    if profile == "haca-evolve":
        baseline["evolve"] = {"scope": evolve_scope}

    atomic_write(entity_root / "state" / "baseline.json", baseline)
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

    # ── Step 7: Summary ──────────────────────────────────────────────────────
    print()
    print(f"  {'─' * W}")
    print(f"  Entity created successfully")
    print(f"  {'─' * W}")
    print(f"  path:         {entity_root}")
    print(f"  profile:      {haca_profile}")
    print(f"  fcp version:  v{fcp_version}")
    print(f"  backend:      {backend} / {model}")
    if api_key_saved:
        print(f"  api key:      saved ({api_key_saved})")
    if profile == "haca-evolve":
        print(f"  scope:")
        print(f"    autonomous evolution:  {'yes' if evolve_scope['autonomous_evolution'] else 'no'}")
        print(f"    autonomous skills:     {'yes' if evolve_scope['autonomous_skills'] else 'no'}")
        print(f"    cmi access:            {evolve_scope['cmi_access']}")
        print(f"    operator memory:       {'yes' if evolve_scope['operator_memory'] else 'no'}")
        renewal = evolve_scope['renewal_days']
        print(f"    renewal:               {'every ' + str(renewal) + ' days' if renewal > 0 else 'disabled'}")
    print(f"  {'─' * W}")
    print(f"  dependencies:")
    print(f"    python {py_str}          ✓")
    print(f"    rich                   — not installed (optional)")
    print(f"    textual                — not installed (optional)")
    print(f"  {'─' * W}")
    print()
    print(f"  First boot will run FAP (First Activation Protocol).")
    print(f"  Run:  cd {entity_root} && ./fcp")
    print()


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
    _print_block("FCP", header_lines, color="\x1b[90m")  # dark gray
    notif_str = f" You have {s['notifications']} new notifications in /inbox." if s["notifications"] else ""
    print(f"Type your message or /help.{notif_str}")


