"""
CLI entry point — FCP §12.1.

Usage (always run from inside the entity root):
  fcp                          — boot and run a session
  fcp init                     — initialise entity root in cwd
  fcp doctor [--fix]           — check/repair without booting
  fcp decommission --archive | --destroy
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from .store import (
    API_KEY_ENV,
    Layout,
    atomic_write,
    load_env_file,
    read_json,
    save_api_key,
)
from . import ui


def _require_entity_root(entity_root: Path) -> None:
    if not (entity_root / ".fcp-entity").exists():
        ui.print_err(f"Not an FCP entity root: {entity_root}")
        ui.print_err("Run 'fcp init' to initialise one, or cd into an existing entity.")
        sys.exit(1)


def main() -> None:
    try:
        _main()
    except KeyboardInterrupt:
        print("\n[interrupted]")
        sys.exit(0)


def _main() -> None:
    load_env_file()
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
        _require_entity_root(entity_root)
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
        _require_entity_root(entity_root)
        _run_doctor(Layout(entity_root), rest)
        return

    if cmd == "decommission":
        from .store import Layout
        _require_entity_root(entity_root)
        _run_decommission(Layout(entity_root), rest)
        return

    if cmd == "model":
        from .store import Layout
        _require_entity_root(entity_root)
        _run_model(Layout(entity_root))
        return

    if cmd == "endure" and rest:
        from .store import Layout
        _require_entity_root(entity_root)
        sub = rest[0]
        if sub == "sync":
            _run_endure_sync(Layout(entity_root))
        elif sub == "origin":
            _run_endure_origin(Layout(entity_root))
        elif sub == "chain":
            _run_endure_chain(Layout(entity_root))
        else:
            ui.print_err(f"Unknown endure subcommand: {sub}")
            print("  usage: fcp endure sync | origin | chain")
            sys.exit(1)
        return

    if cmd == "--auto" and rest:
        from .store import Layout
        _require_entity_root(entity_root)
        _run_auto(Layout(entity_root), rest[0])
        return

    if cmd in ("update", "upgrade"):
        _run_update()
        return

    print(f"unknown command: {cmd}")
    print("usage: fcp [init | model | update | doctor [--fix] | decommission --archive|--destroy | endure sync | --auto <cron_id>]")
    sys.exit(1)


def _print_help() -> None:
    print("""
  fcp                              — boot entity and start session
  fcp init                         — initialize a new entity
  fcp model                        — interactive model picker
  fcp mcp                          — Manager MCP server
  fcp endure sync                  — sync entity root with git remote
  fcp endure origin                — set or update git remote origin
  fcp endure chain                 — display integrity chain
  fcp decommission --archive       — archive entity (reversible)
  fcp decommission --destroy       — destroy entity permanently
  fcp doctor [--fix]               — check integrity; --fix to repair
  fcp --auto <cron_id>             — run scheduled task autonomously in auto:session
  fcp --verbose                    — boot entity with verbose mode enabled
  fcp --debugger[=all|chat|boot]   — boot entity with debugger mode enabled
  fcp update                       — update FCP from the main repository
  
  fcp help                         — this message
""")


# ---------------------------------------------------------------------------
# Update FCP Installation
# ---------------------------------------------------------------------------

def _run_update() -> None:
    # Resolve the physical path in case this was run from a symlink (e.g., ~/.local/bin/fcp)
    # cli.py is at: ~/.fcp/implementations/fcp-ref/fcp_base/cli.py
    # So the FCP root is 3 parents up.
    cli_file = Path(__file__).resolve()
    fcp_root = cli_file.parents[3]

    # Guard: reject if this is running from within an entity root
    # (check if any ancestor between cli_file and fcp_root contains .fcp-entity)
    for ancestor in cli_file.parents:
        if (ancestor / ".fcp-entity").exists():
            ui.print_err("fcp update must be run from the global fcp installation.")
            ui.print_err("Use the 'fcp' command in your PATH, not a local copy.")
            sys.exit(1)
        if ancestor == fcp_root:
            break

    if not (fcp_root / ".git").exists():
        ui.print_err(f"Cannot update: FCP installation at {fcp_root} is not a git repository.")
        sys.exit(1)
        
    print()
    ui.hr("fcp update")
    ui.print_info(f"Checking for updates in {fcp_root}...")
    
    r = subprocess.run(
        ["git", "-C", str(fcp_root), "pull", "origin", "main", "--rebase"],
        capture_output=True, text=True
    )
    
    if r.returncode != 0:
        ui.print_err(f"Update failed. Check your git configuration or network.")
        print(f"Error output:\n{r.stderr}")
        sys.exit(1)
        
    if "Already up to date." in r.stdout or "Current branch main is up to date" in r.stdout:
        ui.print_ok("FCP is already up to date with origin/main.")
    else:
        ui.print_ok("FCP updated successfully.")
        print()
        print(r.stdout.strip())
    print()


# ---------------------------------------------------------------------------
# Normal boot + session loop
# ---------------------------------------------------------------------------

def _run_normal(layout: "Layout") -> None:
    from .boot import run as boot_run, BootError
    from .cpe.base import load_cpe_adapter_from_baseline
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
        adapter = load_cpe_adapter_from_baseline(layout)
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
    from .session import set_session_mode, SessionMode
    from .sleep import run_sleep_cycle
    from .store import read_json
    from .sil import write_notification

    # Set session mode to AUTO (no operator interaction)
    set_session_mode(SessionMode.AUTO)

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


    try:
        from .cpe.base import load_cpe_adapter_from_baseline
        adapter = load_cpe_adapter_from_baseline(layout)
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
    import json
    from .session import set_session_mode, SessionMode
    from .store import atomic_write, read_json
    from .sil import write_notification
    from .exec_ import dispatch

    # Set session mode to AUTO (no operator interaction)
    set_session_mode(SessionMode.AUTO)

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
# Endure Sync — git-based entity backup/restore, outside of session
# ---------------------------------------------------------------------------

def _run_endure_sync(layout: "Layout") -> None:
    """Sync entity root with its git remote.

    Flow:
      1. Verify this is a git repo.
      2. git fetch origin — update remote refs.
      3. Compare local HEAD vs origin/<branch> and report status.
      4. If there are local changes, offer to commit them first.
      5. Present action menu based on divergence state.
      6. Execute chosen action and report result.
    """
    root = str(layout.root)

    def _git(*args: str) -> tuple[int, str, str]:
        r = subprocess.run(
            ["git", "-C", root, *args],
            capture_output=True, text=True,
        )
        return r.returncode, r.stdout.strip(), r.stderr.strip()

    def _git_out(*args: str) -> str:
        _, out, _ = _git(*args)
        return out

    # ── 1. Verify git repo ───────────────────────────────────────────────
    code, _, _ = _git("rev-parse", "--git-dir")
    if code != 0:
        ui.print_err("This entity root is not a git repository.")
        ui.print_err("Run 'git init' inside the entity root and add a remote to use sync.")
        return

    # ── 2. Verify remote exists ──────────────────────────────────────────
    remotes = _git_out("remote")
    if "origin" not in remotes.splitlines():
        ui.print_err("No 'origin' remote configured.")
        ui.print_err("Add one with: git remote add origin <url>")
        return

    # ── 3. Fetch ─────────────────────────────────────────────────────────
    ui.print_info("Fetching from origin...")
    code, _, err = _git("fetch", "origin")
    if code != 0:
        ui.print_err(f"git fetch failed: {err}")
        return

    # ── 4. Determine current branch and tracking ref ─────────────────────
    branch = _git_out("rev-parse", "--abbrev-ref", "HEAD")
    if branch == "HEAD":
        ui.print_err("Detached HEAD — cannot sync. Check out a branch first.")
        return

    remote_ref = f"origin/{branch}"
    remote_exists_code, _, _ = _git("rev-parse", "--verify", remote_ref)

    # ── 5. Check working tree status ─────────────────────────────────────
    _, status_out, _ = _git("status", "--porcelain")
    has_local_changes = bool(status_out.strip())

    # ── 6. Compare local vs remote ───────────────────────────────────────
    print()
    ui.hr("endure sync")

    if remote_exists_code != 0:
        ui.print_info(f"Branch '{branch}' has no upstream on origin yet.")
        ahead = int(_git_out("rev-list", "--count", "HEAD") or "0")
        behind = 0
    else:
        ahead_str = _git_out("rev-list", "--count", f"{remote_ref}..HEAD")
        behind_str = _git_out("rev-list", "--count", f"HEAD..{remote_ref}")
        ahead = int(ahead_str or "0")
        behind = int(behind_str or "0")

    # Status report
    if has_local_changes:
        ui.print_warn(f"Uncommitted local changes detected.")
    if remote_exists_code != 0:
        ui.print_info(f"Local branch '{branch}' not yet pushed to origin.")
    elif ahead == 0 and behind == 0:
        ui.print_ok("Entity is in sync with origin.")
    elif ahead > 0 and behind == 0:
        ui.print_info(f"Local is {ahead} commit(s) ahead of origin/{branch}.")
    elif ahead == 0 and behind > 0:
        ui.print_info(f"Local is {behind} commit(s) behind origin/{branch}.")
    else:
        ui.print_warn(f"Diverged: {ahead} local commit(s), {behind} remote commit(s).")

    print()

    # ── 7. Build action menu ─────────────────────────────────────────────
    actions: list[str] = []

    if has_local_changes:
        actions.append("commit local changes")
    if remote_exists_code != 0 or ahead > 0:
        actions.append(f"push to origin/{branch}")
    if behind > 0:
        actions.append(f"pull from origin/{branch} (fast-forward)")
    if ahead > 0 and behind > 0:
        actions.append(f"rebase local on origin/{branch}")
    actions.append("show git status")
    actions.append("show log (last 10)")
    actions.append("abort — do nothing")

    choice = ui.pick_one("Action", actions, default_idx=0)
    if choice is None or choice == "abort — do nothing":
        ui.print_info("Sync aborted.")
        return

    print()

    # ── 8. Execute chosen action ─────────────────────────────────────────
    if choice == "commit local changes":
        msg = ui.ask("Commit message", "endure sync")
        if not msg:
            msg = f"endure sync {int(time.time())}"
        code, out, err = _git("add", "-A")
        if code != 0:
            ui.print_err(f"git add failed: {err}")
            return
        code, out, err = _git("commit", "-m", msg)
        if code != 0:
            ui.print_err(f"git commit failed: {err or out}")
        else:
            ui.print_ok(f"Committed: {out.splitlines()[0] if out else 'ok'}")

    elif choice.startswith("push to origin/"):
        code, out, err = _git("push", "origin", branch)
        if code != 0:
            ui.print_err(f"git push failed: {err}")
        else:
            ui.print_ok(f"Pushed to origin/{branch}.")

    elif choice.startswith("pull from origin/"):
        code, out, err = _git("pull", "--ff-only", "origin", branch)
        if code != 0:
            ui.print_err(f"git pull failed: {err}")
            ui.print_info("Tip: use 'rebase local on origin' if fast-forward is not possible.")
        else:
            ui.print_ok(f"Pulled: {out.splitlines()[0] if out else 'ok'}")

    elif choice.startswith("rebase local on origin/"):
        code, out, err = _git("rebase", f"origin/{branch}")
        if code != 0:
            ui.print_err(f"git rebase failed: {err}")
            ui.print_err("Resolve conflicts manually, then run 'git rebase --continue'.")
        else:
            ui.print_ok("Rebase complete.")

    elif choice == "show git status":
        code, out, _ = _git("status")
        print(out)

    elif choice == "show log (last 10)":
        code, out, _ = _git("log", "--oneline", "-10")
        print(out)

    print()


# ---------------------------------------------------------------------------
# Endure Origin — configure git remote
# ---------------------------------------------------------------------------

def _run_endure_origin(layout: "Layout") -> None:
    """Set or update the 'origin' git remote for this entity root."""
    root = str(layout.root)

    def _git(*args: str) -> tuple[int, str, str]:
        r = subprocess.run(
            ["git", "-C", root, *args],
            capture_output=True, text=True,
        )
        return r.returncode, r.stdout.strip(), r.stderr.strip()

    # Verify git repo
    code, _, _ = _git("rev-parse", "--git-dir")
    if code != 0:
        ui.print_err("This entity root is not a git repository.")
        ui.print_err("Run 'git init' inside the entity root first.")
        return

    print()
    ui.hr("endure origin")

    # Show current origin if any
    code, current_url, _ = _git("remote", "get-url", "origin")
    if code == 0:
        ui.print_info(f"Current origin: {current_url}")
    else:
        ui.print_info("No origin remote configured yet.")

    print()
    new_url = ui.ask("Remote URL (leave blank to cancel)", "")
    if not new_url:
        ui.print_info("Cancelled.")
        return

    if code == 0:
        # origin exists — update it
        set_code, _, err = _git("remote", "set-url", "origin", new_url)
        if set_code != 0:
            ui.print_err(f"Failed to update origin: {err}")
        else:
            ui.print_ok(f"origin updated → {new_url}")
    else:
        # origin does not exist — add it
        add_code, _, err = _git("remote", "add", "origin", new_url)
        if add_code != 0:
            ui.print_err(f"Failed to add origin: {err}")
        else:
            ui.print_ok(f"origin added → {new_url}")

    print()


# ---------------------------------------------------------------------------
# Endure Chain — display integrity chain
# ---------------------------------------------------------------------------

def _run_endure_chain(layout: "Layout") -> None:
    """Display the integrity chain entries."""
    from .operator import print_integrity_chain
    print_integrity_chain(layout)


# ---------------------------------------------------------------------------
# Doctor — operates without booting
# ---------------------------------------------------------------------------

def _run_doctor(layout: "Layout", args: list[str]) -> None:
    from .operator import run_doctor
    run_doctor(layout, fix="--fix" in args, clear_sentinels=True)


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
        ui.print_warn(f"Partial decommission detected (phase: {partial.get('phase')}, mode: {partial.get('mode')}).")
        if not ui.confirm("Resume?", default=False):
            print("  Aborted.")
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
        ui.print_warn(f"This will permanently destroy the entity at {layout.root}.")
        if not ui.confirm("Permanently destroy entity?", default=False):
            print("  Aborted.")
            sys.exit(0)

    try:
        boot_run(layout)
    except FAPError as exc:
        print(f"[FAP FAILED] {exc}")
        sys.exit(1)
    except BootError as exc:
        print(f"[BOOT FAILED] {exc}")
        sys.exit(1)

    from .cpe.base import load_cpe_adapter_from_baseline
    adapter = load_cpe_adapter_from_baseline(layout)
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

def _get_entity_profile(layout: "Layout") -> str:
    """Read entity profile from .fcp-entity marker. Defaults to 'haca-core'."""
    entity_marker_path = layout.root / ".fcp-entity"
    if entity_marker_path.exists():
        try:
            marker = json.loads(entity_marker_path.read_text(encoding="utf-8"))
            return marker.get("profile", "haca-core")
        except Exception:
            pass
    return "haca-core"


def _get_allowed_backends(profile: str) -> list[str]:
    """Filter backends based on entity profile.

    - haca-core: excludes 'pairing' (has direct entity access)
    - haca-evolve: includes 'pairing' (uses it as opaque CPE backend)
    """
    from .cpe.base import BACKENDS

    if profile == "haca-evolve":
        return BACKENDS
    else:  # haca-core
        return [b for b in BACKENDS if b != "pairing"]


def _run_model(layout: "Layout") -> None:
    from .cpe.base import BACKENDS, KNOWN_MODELS, fetch_ollama_models
    from .store import read_json, atomic_write

    try:
        baseline = read_json(layout.baseline)
    except Exception:
        print("[ERROR] Could not read baseline.json — run fcp init first.")
        sys.exit(1)

    cpe_cfg = baseline.get("cpe", {})
    current_backend = cpe_cfg.get("backend", "ollama")
    current_model = cpe_cfg.get("model", "")

    # Get allowed backends based on entity profile
    profile = _get_entity_profile(layout)
    allowed_backends = _get_allowed_backends(profile)

    # Build flat list of "backend:model" labels
    items: list[str] = []
    pairs: list[tuple[str, str]] = []  # (backend, model) parallel to items

    for backend in allowed_backends:
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
    chosen_label = ui.pick_one("Select provider and model", items, default_idx, indent="  ")
    # find the pair that matches the chosen label (strip marker)
    chosen_idx = next(i for i, lbl in enumerate(items) if lbl == chosen_label)
    backend, model = pairs[chosen_idx]

    # API key (skip for ollama)
    if backend != "ollama":
        env_var = API_KEY_ENV.get(backend, "")
        if env_var:
            current_key_hint = "already configured" if os.environ.get(env_var) else "not configured"
            api_key = ui.ask(f"{env_var} (leave blank to keep)", default=current_key_hint if not os.environ.get(env_var) else "")
            # treat hint string as empty — only save if user typed a real key
            if api_key and api_key != current_key_hint:
                save_api_key(layout.root.name, env_var, api_key)

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


def _write_entity_gitignore(entity_root: Path) -> None:
    """Write a .gitignore tailored for an FCP entity root.

    Excludes volatile runtime artefacts that should not be version-controlled:
    session tokens, runtime logs, transient I/O queues, snapshots, etc.
    Structural and mnemonic state (persona, skills, memory, baseline, chain)
    are intentionally tracked.
    """
    content = """\
# FCP entity root — generated by fcp init

# Volatile runtime artefacts — do not commit
io/inbox/
io/spool/
state/sentinels/
state/snapshots/
state/operator_notifications/
state/integrity.log
state/distress.beacon
state/first-stimuli.json
state/pending-closure.json

# Ignore the dynamic entity workspace completely to prevent nested repository collisions
workspace/

# (Optional) If you need the workspace folder to exist upon cloning the entity, 
# but want to ignore its contents, use this pattern instead:
# workspace/*
# !workspace/.gitkeep

# Python
__pycache__/
*.py[cod]

# Environment / secrets
.env
.fcp.env
"""
    gitignore = entity_root / ".gitignore"
    gitignore.write_text(content, encoding="utf-8")


def _run_init(fcp_ref_root: Path) -> None:
    """Interactive init — creates a new entity root from fcp-ref templates."""
    fcp_version = _read_fcp_version(fcp_ref_root)

    # ── Header ──────────────────────────────────────────────────────────────
    print()
    ui.hr()
    print(f"  FCP — Filesystem Cognitive Platform v{fcp_version}")
    print(f"  HACA — Host-Agnostic Cognitive Architecture v1.0")
    ui.hr()
    print(f"  FCP is a reference implementation of HACA and may contain")
    print(f"  errors. HACA is an open architecture specification for")
    print(f"  persistent cognitive entities.")
    print()
    print(f"  Contributions are welcome. Report issues and security")
    print(f"  vulnerabilities at: https://github.com/HACA-org/HACA")
    ui.hr()
    print()
    ui.print_warn("WARNING: EXPERIMENTAL SYSTEM")
    ui.hr()
    print(f"  Despite integrated safety mechanisms, this is experimental")
    print(f"  software. Use may result in data loss, host environment")
    print(f"  damage, or leakage of sensitive information.")
    print()
    print(f"  Do not use in production without a prior security review.")
    print(f"  By continuing, you acknowledge and accept these risks.")
    ui.hr()
    print()
    if not ui.confirm("Continue?"):
        sys.exit(0)

    # ── Step 1: Destination ─────────────────────────────────────────────────
    ui.hr("1. Entity destination")
    print()
    print("  Where should the entity root be created?")
    print("  Leave blank to use the current directory.")
    print()
    dest_input = ui.ask("Path", str(Path.cwd()))
    entity_root = Path(dest_input).expanduser().resolve()

    # Detection logic
    is_fcp_ref = (entity_root / ".fcp-base").exists()
    is_fcp_entity = (entity_root / ".fcp-entity").exists() or (entity_root / "state" / "baseline.json").exists()
    is_nonempty = entity_root.exists() and any(entity_root.iterdir())

    if is_fcp_ref:
        print()
        ui.print_err(f"{entity_root} is the HACA/FCP source directory (contains .fcp-base).")
        print("          You cannot install an entity here. Choose another path.")
        sys.exit(1)

    keep_persona = False
    keep_skills = False
    keep_boot = False
    keep_hooks = False
    keep_tests = False
    keep_fcp_base = False
    keep_state = False
    keep_io = False

    if is_fcp_entity:
        print()
        ui.print_warn(f"Existing FCP entity detected at {entity_root}.")
        action_items = [
            "Reset to FAP  — wipe dynamic state (state/, memory/, io/) and restart",
            "Update        — selectively overwrite components from templates",
            "Cancel",
        ]
        choice_label = ui.pick_one("Select an action", action_items, default_idx=0, indent="  ")
        choice_idx = action_items.index(choice_label)

        if choice_idx == 2:  # Cancel
            sys.exit(0)
        elif choice_idx == 0:  # Reset to FAP
            for d in ["state", "memory", "io"]:
                p = entity_root / d
                if p.exists() and p.is_dir():
                    for sub in p.iterdir():
                        if sub.name != "baseline.json":
                            if sub.is_dir(): shutil.rmtree(sub)
                            else: sub.unlink()
            # Recreate expected memory subdirectories so boot/MIL don't fail.
            for subdir in ["memory/episodic", "memory/semantic", "memory/active_context"]:
                (entity_root / subdir).mkdir(parents=True, exist_ok=True)
            print()
            ui.print_ok("Dynamic state cleared. Entity is ready for FAP.")
            print(f"      Run: cd {entity_root} && ./fcp")
            print()
            sys.exit(0)
        else:  # Update
            ui.hr("Update")
            print("      Checked = keep existing.  Unchecked = overwrite from template.")
            print()

            # Ordered alphabetically
            update_items = [
                "boot.md    — operational rules and boot protocol",
                "fcp_base/  — FCP core engine modules",
                "hooks/     — event-driven lifecycle scripts",
                "io/        — inbox and spool (runtime I/O)",
                "persona/   — personality and operator history",
                "skills/    — custom tools and reasoning units",
                "state/     — baseline, integrity, session state",
                "tests/     — unit and integrated validations",
            ]
            update_defaults = [True, True, True, True, True, True, True, True]

            states = ui.pick_many(
                "Components to KEEP (uncheck to overwrite from template)",
                update_items,
                update_defaults,
                indent="      ",
            )
            (keep_boot, keep_fcp_base, keep_hooks, keep_io,
             keep_persona, keep_skills, keep_state, keep_tests) = states

            # Read current profile from .fcp-entity to resolve persona template dir
            entity_marker_path = entity_root / ".fcp-entity"
            try:
                _marker = json.loads(entity_marker_path.read_text(encoding="utf-8"))
                _profile = _marker.get("profile", "haca-core")
            except Exception:
                _profile = "haca-core"
            _profile_dir = fcp_ref_root / ("fcp-core" if _profile == "haca-core" else "fcp-evolve")

            ui.hr("Applying updates")
            print()

            # Copy only unchecked components
            for _src, _dst_name, _keep in [
                (fcp_ref_root / "boot.md",    "boot.md",   keep_boot),
                (fcp_ref_root / "fcp_base",   "fcp_base",  keep_fcp_base),
                (fcp_ref_root / "hooks",      "hooks",     keep_hooks),
                (fcp_ref_root / "skills",     "skills",    keep_skills),
                (fcp_ref_root / "tests",      "tests",     keep_tests),
                (_profile_dir / "persona",    "persona",   keep_persona),
            ]:
                if _keep:
                    print(f"  [·] Keeping   {_dst_name}")
                    continue
                if not _src.exists():
                    continue
                _dst = entity_root / _dst_name
                print(f"  [↓] Updating  {_dst_name}")
                if _src.is_dir():
                    if _dst.exists():
                        shutil.rmtree(_dst)
                    shutil.copytree(_src, _dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
                else:
                    shutil.copy2(_src, _dst)

            # Also copy the fcp entrypoint (always — it's not user-editable)
            _fcp_src = fcp_ref_root / "fcp"
            if _fcp_src.exists():
                _fcp_dst = entity_root / "fcp"
                shutil.copy2(_fcp_src, _fcp_dst)
                _fcp_dst.chmod(0o755)

            # Wipe dynamic dirs only if explicitly unchecked
            if not keep_state:
                print(f"  [↓] Wiping    state/")
                _p = entity_root / "state"
                if _p.exists():
                    for _sub in _p.iterdir():
                        if _sub.name != "baseline.json":
                            if _sub.is_dir(): shutil.rmtree(_sub)
                            else: _sub.unlink()
            else:
                print(f"  [·] Keeping   state/")

            if not keep_io:
                print(f"  [↓] Wiping    io/")
                _p = entity_root / "io"
                if _p.exists():
                    shutil.rmtree(_p)
            else:
                print(f"  [·] Keeping   io/")

            # Recreate any missing runtime dirs (idempotent)
            for _d in [
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
                _d.mkdir(parents=True, exist_ok=True)

            # Git init if not already a repo
            _git_init = False
            if not (entity_root / ".git").exists():
                print()
                _git_init = ui.confirm("Initialise a git repository in the entity root?", default=True)
            if _git_init:
                _git_ok = False
                try:
                    _fcp_ver = _read_fcp_version(fcp_ref_root)
                    subprocess.run(["git", "init", str(entity_root)], check=True, capture_output=True)
                    _write_entity_gitignore(entity_root)
                    subprocess.run(["git", "-C", str(entity_root), "add", "."], check=True, capture_output=True)
                    subprocess.run(
                        ["git", "-C", str(entity_root), "commit", "-m",
                         f"chore: update entity (fcp v{_fcp_ver})"],
                        check=True, capture_output=True,
                    )
                    _git_ok = True
                except subprocess.CalledProcessError as _exc:
                    print(f"  [!] git failed: {_exc.stderr.decode().strip()}")
                except FileNotFoundError:
                    print("  [!] git not found — skipping.")

            print()
            ui.hr()
            print(f"  Entity updated successfully")
            ui.hr()
            print(f"  path:    {entity_root}")
            print(f"  profile: {_marker.get('haca_profile', _profile)}")
            if _git_init:
                print(f"  git:     {'initial commit created' if _git_ok else 'init failed (see above)'}")
            ui.hr()
            print()
            return

    elif is_nonempty:
        print()
        ui.print_err(f"{entity_root} is not empty and is not an FCP entity.")
        print("  FCP entities must be initialised in an empty directory.")
        print("  Choose an empty or non-existing directory and try again.")
        print()
        sys.exit(1)

    # ── Step 2: Profile ─────────────────────────────────────────────────────
    ui.hr("2. Profile")
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
    profile_choice = ui.pick_one("Profile", profile_items, default_idx=0, indent="  ")
    profile = "haca-core" if profile_items.index(profile_choice) == 0 else "haca-evolve"
    haca_profile = "HACA-Core-1.0.0" if profile == "haca-core" else "HACA-Evolve-1.0.0"

    # ── Step 3: Evolve scope (only for haca-evolve) ─────────────────────────
    evolve_scope: dict = {}
    if profile == "haca-evolve":
        ui.hr("3. Autonomous scope")
        print()
        print("  Define what this entity is authorised to do autonomously.")
        print("  These permissions can be revoked by re-initialising.")
        print()

        print("  [1] Autonomous structural evolution")
        print("      The entity may modify its own entity root freely, including")
        print("      its own code. WARNING: this grants unrestricted write access")
        print("      to the entire entity root.")
        allow_evolution = ui.confirm("Authorise?", indent="      ")

        print()
        print("  [2] Autonomous skill creation and installation")
        print("      The entity may create and install new skills without approval.")
        print("      WARNING: skills run as Python code with full access to the")
        print("      entity root. Only enable if you trust the entity's judgment.")
        allow_skills = ui.confirm("Authorise?", indent="      ")

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
        cmi_choice = ui.pick_one("CMI access", cmi_items, default_idx=0, indent="      ")
        cmi_scope = cmi_choice.split()[0]

        print()
        print("  [4] Operator memory")
        print("      The entity may save your preferences and information across")
        print("      sessions. The entity will NEVER share your secrets (API keys,")
        print("      tokens, passwords). NOTE: you are also responsible for not")
        print("      sharing secrets directly in conversation — the entity cannot")
        print("      protect what it never receives.")
        allow_memory = ui.confirm("Authorise?", indent="      ")

        print()
        print("  [5] Scope renewal interval")
        print("      These authorisations will expire and the entity will pause")
        print("      until you renew them. Enter 0 to disable expiry.")
        while True:
            renewal_input = ui.ask("Renewal interval in days", "30")
            try:
                renewal_days = int(renewal_input)
                if renewal_days >= 0:
                    break
            except ValueError:
                pass
            ui.print_err("Please enter a non-negative integer.")

        evolve_scope = {
            "autonomous_evolution": allow_evolution,
            "autonomous_skills": allow_skills,
            "cmi_access": cmi_scope,
            "operator_memory": allow_memory,
            "renewal_days": renewal_days,
        }


    # ── Step 4: CPE backend and model ────────────────────────────────────────
    ui.hr("4. CPE backend and model")
    print()
    from .cpe.base import KNOWN_MODELS, fetch_ollama_models

    # Get allowed backends based on profile
    allowed_backends = _get_allowed_backends(profile)
    backend = ui.pick_one("Backend", allowed_backends, indent="  ")

    api_key_saved: str | None = None
    if backend == "ollama":
        ollama_models = fetch_ollama_models()
        if ollama_models:
            model = ui.pick_one("Model", ollama_models, indent="  ")
        else:
            model = ui.ask("Model", "llama3.2")
    elif backend == "pairing":
        model_list = KNOWN_MODELS[backend]
        model = ui.pick_one("Model", model_list, indent="  ")
    else:
        model_list = KNOWN_MODELS[backend]
        model = ui.pick_one("Model", model_list, indent="  ")
        env_var = API_KEY_ENV[backend]
        current_key_hint = "already configured" if os.environ.get(env_var) else ""
        default_hint = current_key_hint if current_key_hint else ""
        api_key = ui.ask(f"{env_var} (leave blank to keep)", default_hint)
        if api_key and api_key != current_key_hint:
            save_api_key(entity_root.name, env_var, api_key)
            api_key_saved = env_var

    # ── Step 5: Copy snapshot and create runtime dirs ────────────────────────
    ui.hr("5. Creating entity")
    print()
    entity_root.mkdir(parents=True, exist_ok=True)

    profile_dir = fcp_ref_root / ("fcp-core" if profile == "haca-core" else "fcp-evolve")

    # Copy structural content
    for src, dst_name in [
        (fcp_ref_root / "fcp_base",  "fcp_base"),
        (fcp_ref_root / "skills",    "skills"),
        (fcp_ref_root / "hooks",     "hooks"),
        (fcp_ref_root / "tests",     "tests"),
        (fcp_ref_root / "boot.md",   "boot.md"),
        (profile_dir / "persona",    "persona"),
    ]:
        if dst_name == "persona" and keep_persona:
            print(f"  [·] Preserving existing persona/")
            continue
        if dst_name == "skills" and keep_skills:
            print(f"  [·] Preserving existing skills/")
            continue
        if dst_name == "fcp_base" and keep_fcp_base:
            print(f"  [·] Preserving existing fcp_base/")
            continue
        if dst_name == "tests" and keep_tests:
            print(f"  [·] Preserving existing tests/")
            continue
        if dst_name == "hooks" and keep_hooks:
            print(f"  [·] Preserving existing hooks/")
            continue
        if dst_name == "boot.md" and keep_boot:
            print(f"  [·] Preserving existing boot.md")
            continue

        dst = entity_root / dst_name
        if not src.exists(): continue
        if src.is_dir():
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
        elif src.is_file():
            shutil.copy2(src, dst)

    # ── Step 6: Marker and Runtime dirs ──────────────────────────────────────
    # Create .fcp-entity marker
    entity_marker = {
        "version": fcp_version,
        "profile": profile,
        "haca_profile": haca_profile,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (entity_root / ".fcp-entity").write_text(json.dumps(entity_marker, indent=2), encoding="utf-8")

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

    # ── Git init + initial commit ────────────────────────────────────────────
    git_init = False
    if not (entity_root / ".git").exists():
        print()
        git_init = ui.confirm("Initialise a git repository in the entity root?", default=True)

    if git_init:
        git_ok = False
        try:
            subprocess.run(["git", "init", str(entity_root)], check=True, capture_output=True)
            # Write entity-root .gitignore before staging
            _write_entity_gitignore(entity_root)
            subprocess.run(["git", "-C", str(entity_root), "add", "."], check=True, capture_output=True)
            subprocess.run(
                ["git", "-C", str(entity_root), "commit", "-m", f"chore: init entity (fcp v{fcp_version}, {haca_profile})"],
                check=True, capture_output=True,
            )
            git_ok = True
        except subprocess.CalledProcessError as exc:
            print(f"  [!] git failed: {exc.stderr.decode().strip()}")
        except FileNotFoundError:
            print("  [!] git not found — skipping.")

    # ── Step 7: Summary ──────────────────────────────────────────────────────
    print()
    ui.hr()
    print(f"  Entity created successfully")
    ui.hr()
    print(f"  path:         {entity_root}")
    print(f"  profile:      {haca_profile}")
    print(f"  fcp version:  v{fcp_version}")
    print(f"  backend:      {backend} / {model}")
    if api_key_saved:
        print(f"  api key:      saved ({api_key_saved})")
    if git_init:
        print(f"  git:          {'initial commit created' if git_ok else 'init failed (see above)'}")
    if profile == "haca-evolve":
        print(f"  scope:")
        print(f"    autonomous evolution:  {'yes' if evolve_scope['autonomous_evolution'] else 'no'}")
        print(f"    autonomous skills:     {'yes' if evolve_scope['autonomous_skills'] else 'no'}")
        print(f"    cmi access:            {evolve_scope['cmi_access']}")
        print(f"    operator memory:       {'yes' if evolve_scope['operator_memory'] else 'no'}")
        renewal = evolve_scope['renewal_days']
        print(f"    renewal:               {'every ' + str(renewal) + ' days' if renewal > 0 else 'disabled'}")
    ui.hr()
    print()
    print(f"  First boot will run FAP (First Activation Protocol).")
    print(f"  Run:  cd {entity_root} && ./fcp")
    print()


def _print_block(label: str, lines: list, color: str = "\x1b[96m") -> None:
    """Print a bordered block with a colored header label and closing border."""
    width = ui._W
    border = "─" * (width - len(label) - 3)
    print(f"{color}╭─ {label} {border}╮{ui.RESET}")
    for line in lines:
        print(f"{ui.DIM}│{ui.RESET} {line}")
    print(f"{color}╰{'─' * width}╯{ui.RESET}")


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


