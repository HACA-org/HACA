"""
CLI runtime commands — normal, auto, auto-worker, model, doctor, decommission, update,
status, agenda.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from ..store import API_KEY_ENV, atomic_write, load_baseline, read_json, save_api_key
from .. import ui
from .ui import print_boot_header

if TYPE_CHECKING:
    from ..store import Layout


# ---------------------------------------------------------------------------
# Normal boot + session loop
# ---------------------------------------------------------------------------

def run_normal(layout: "Layout") -> None:
    from ..boot import run as boot_run, BootError
    from ..cpe.base import load_cpe_adapter_from_baseline
    from ..fap import FAPError
    from ..operator import handle_platform_command, present_notifications, present_evolution_proposals
    from ..session import run_session
    from ..sleep import run_sleep_cycle

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

    print_boot_header(layout, index)

    while present_evolution_proposals(layout):
        pass

    while True:
        close_reason = run_session(layout, adapter, index)

        present_evolution_proposals(layout)

        from ..hooks import run_hook
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
# Auto session
# ---------------------------------------------------------------------------

def run_auto(layout: "Layout", cron_id: str) -> None:
    """Execute a scheduled task autonomously, without an Operator session."""
    from ..boot import run as boot_run, BootError
    from ..fap import FAPError
    from ..session_mode import set_session_mode, SessionMode
    from ..sleep import run_sleep_cycle
    from ..sil import write_notification

    set_session_mode(SessionMode.AUTO)

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

    if executor == "worker":
        run_auto_worker(layout, task, wake_up_message)
        return

    try:
        boot_run(layout)
    except FAPError as exc:
        print(f"[FAP FAILED] {exc}")
        sys.exit(1)
    except BootError as exc:
        print(f"[BOOT FAILED] {exc}")
        sys.exit(1)

    try:
        from ..cpe.base import load_cpe_adapter_from_baseline
        adapter = load_cpe_adapter_from_baseline(layout)
    except Exception as exc:
        print(f"[CPE ERROR] {exc}")
        sys.exit(1)

    index: dict = {}
    if layout.skills_index.exists():
        index = read_json(layout.skills_index)

    from ..stimuli import inject_wakeup
    inject_wakeup(layout, cron_id, wake_up_message)

    from ..session import run_session
    run_session(layout, adapter, index)

    try:
        run_sleep_cycle(layout)
    except Exception as exc:
        print(f"[SLEEP CYCLE ERROR] {exc}")

    task["last_run"] = _dt.datetime.utcnow().isoformat() + "Z"
    atomic_write(layout.agenda, agenda)

    write_notification(layout, "auto_session_complete", {
        "cron_id": cron_id,
        "description": description,
        "last_run": task["last_run"],
    })
    print(f"[FCP-Auto] complete — {cron_id}")


def run_auto_worker(layout: "Layout", task: dict, wake_up_message: str) -> None:
    """Run a worker_skill task directly without a CPE session."""
    from ..session_mode import set_session_mode, SessionMode
    from ..sil import write_notification
    from ..exec_ import dispatch

    set_session_mode(SessionMode.AUTO)

    index: dict = {}
    if layout.skills_index.exists():
        index = read_json(layout.skills_index)

    cron_id = task.get("id", "")
    description = task.get("description", cron_id)

    context_parts = [
        "[task instructions]",
        task.get("task") or "(no instructions provided)",
        "",
        "[environment]",
    ]
    workspace_focus_file = layout.root / "state" / "workspace_focus.json"
    if workspace_focus_file.exists():
        try:
            wf = json.loads(workspace_focus_file.read_text(encoding="utf-8"))
            context_parts.append(f"workspace_focus: {wf.get('path', '(unset)')}")
        except Exception:
            context_parts.append("workspace_focus: (unavailable)")
    else:
        context_parts.append("workspace_focus: (not set)")
    context = "\n".join(context_parts)

    persona = (
        task.get("persona")
        or "You are an autonomous FCP worker executing a scheduled task. "
           "Act on the stimulus, follow the task instructions, and return a structured result."
    )

    try:
        result = dispatch(layout, "worker_skill", {
            "task": wake_up_message,
            "context": context,
            "persona": persona,
        }, index)
    except Exception as exc:
        result = f"error: {exc}"

    now = _dt.datetime.utcnow().isoformat() + "Z"

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
# Model picker
# ---------------------------------------------------------------------------

def _get_entity_profile(layout: "Layout") -> str:
    entity_marker_path = layout.root / ".fcp-entity"
    if entity_marker_path.exists():
        try:
            marker = json.loads(entity_marker_path.read_text(encoding="utf-8"))
            return marker.get("profile", "haca-core")
        except Exception:
            pass
    return "haca-core"


def _get_allowed_backends(profile: str) -> list[str]:
    from ..cpe.base import BACKENDS
    if profile == "haca-evolve":
        return BACKENDS
    return [b for b in BACKENDS if b != "pairing"]


def run_model(layout: "Layout") -> None:
    from ..cpe.base import BACKENDS, KNOWN_MODELS, fetch_ollama_models

    try:
        baseline = read_json(layout.baseline)
    except Exception:
        print("[ERROR] Could not read baseline.json — run fcp init first.")
        sys.exit(1)

    cpe_cfg = baseline.get("cpe", {})
    current_backend = cpe_cfg.get("backend", "ollama")
    current_model = cpe_cfg.get("model", "")

    profile = _get_entity_profile(layout)
    allowed_backends = _get_allowed_backends(profile)

    items: list[str] = []
    pairs: list[tuple[str, str]] = []

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
    chosen_idx = next(i for i, lbl in enumerate(items) if lbl == chosen_label)
    backend, model = pairs[chosen_idx]

    if backend != "ollama":
        env_var = API_KEY_ENV.get(backend, "")
        if env_var:
            current_key_hint = "already configured" if os.environ.get(env_var) else "not configured"
            api_key = ui.ask(f"{env_var} (leave blank to keep)", default=current_key_hint if not os.environ.get(env_var) else "")
            if api_key and api_key != current_key_hint:
                save_api_key(layout.root.name, env_var, api_key)

    cpe_cfg["backend"] = backend
    cpe_cfg["model"] = model
    baseline["cpe"] = cpe_cfg
    atomic_write(layout.baseline, baseline)
    print(f"[FCP] Model set to {backend}:{model}")


# ---------------------------------------------------------------------------
# Doctor and Decommission
# ---------------------------------------------------------------------------

def run_doctor(layout: "Layout", args: list[str]) -> None:
    from ..operator import run_doctor
    run_doctor(layout, fix="--fix" in args, clear_sentinels=True)


def run_decommission(layout: "Layout", args: list[str]) -> None:
    from ..boot import run as boot_run, BootError
    from ..fap import FAPError
    from ..acp import make as acp_make
    from ..operator import present_evolution_proposals
    from ..session import run_session
    from ..sleep import run_sleep_cycle
    from .. import decommission as _decom

    do_archive = "--archive" in args
    do_destroy = "--destroy" in args

    if not do_archive and not do_destroy:
        print("decommission requires --archive or --destroy")
        sys.exit(1)

    mode = "archive" if do_archive else "destroy"

    partial = _decom.detect_partial(layout)
    if partial:
        ui.print_warn(f"Partial decommission detected (phase: {partial.get('phase')}, mode: {partial.get('mode')}).")
        if not ui.confirm("Resume?", default=False):
            print("  Aborted.")
            sys.exit(0)
        mode = partial.get("mode", mode)
        def _sleep_fn() -> None:
            present_evolution_proposals(layout)
            run_sleep_cycle(layout)
        _decom.run(layout, mode, _sleep_fn, partial=partial)
        return

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

    from ..cpe.base import load_cpe_adapter_from_baseline
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
# Update
# ---------------------------------------------------------------------------

def run_update() -> None:
    cli_file = Path(__file__).resolve()
    fcp_root = cli_file.parents[4]  # cli/ -> fcp_base/ -> fcp-ref/ -> implementations/ -> HACA/

    # Guard: reject if running from within an entity root
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
        ui.print_err("Update failed. Check your git configuration or network.")
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
# Status — entity overview without booting a session
# ---------------------------------------------------------------------------

def run_status(layout: "Layout") -> None:
    """Print entity status overview (no session required)."""
    from ..sil import beacon_is_active

    print()
    ui.hr("fcp status")

    # baseline / model
    try:
        baseline = read_json(layout.baseline)
        cpe = baseline.get("cpe", {})
        backend = cpe.get("backend", "?")
        model = cpe.get("model", "?")
        ui.print_info(f"model          : {backend}:{model}")
    except Exception:
        ui.print_warn("baseline.json unreadable")

    # session token
    token_active = layout.session_token.exists()
    ui.print_info(f"session token  : {'active' if token_active else 'inactive'}")

    # session store size
    session_size = layout.session_store.stat().st_size if layout.session_store.exists() else 0
    ui.print_info(f"session store  : {ui.format_bytes(session_size)}")

    # workspace focus
    wf = ""
    if layout.workspace_focus.exists():
        try:
            wf = str(read_json(layout.workspace_focus).get("path", ""))
        except Exception:
            pass
    ui.print_info(f"workspace      : {wf or '(not set)'}")

    # distress beacon
    if beacon_is_active(layout):
        ui.print_warn("distress beacon: ACTIVE")
    else:
        ui.print_info("distress beacon: clear")

    # notifications
    notif_count = 0
    if layout.operator_notifications_dir.exists():
        notif_count = sum(1 for _ in layout.operator_notifications_dir.iterdir())
    if notif_count:
        ui.print_warn(f"notifications  : {notif_count} pending")
    else:
        ui.print_info("notifications  : none")

    # memory
    mem_count = 0
    for subdir in ("episodic", "semantic"):
        d = layout.root / "memory" / subdir
        if d.exists():
            mem_count += sum(1 for _ in d.iterdir() if _.is_file())
    ui.print_info(f"memories       : {mem_count}")

    print()


# ---------------------------------------------------------------------------
# Agenda — list scheduled tasks without booting a session
# ---------------------------------------------------------------------------

def run_agenda(layout: "Layout") -> None:
    """List scheduled tasks from agenda.json (no session required)."""
    print()
    ui.hr("fcp agenda")

    if not layout.agenda.exists():
        ui.print_info("No agenda found. Tasks are created via /cron add in-session.")
        print()
        return

    try:
        agenda = json.loads(layout.agenda.read_text(encoding="utf-8"))
    except Exception as exc:
        ui.print_err(f"Could not read agenda: {exc}")
        print()
        return

    tasks = agenda.get("tasks", [])
    if not tasks:
        ui.print_info("Agenda is empty.")
        print()
        return

    for task in tasks:
        tid = task.get("id", "?")
        desc = task.get("description", tid)
        status = task.get("status", "?")
        schedule = task.get("schedule", "")
        last_run = task.get("last_run", "")
        executor = task.get("executor", "cpe")

        status_mark = "[√]" if status == "approved" else "[!]" if status == "pending" else "[ ]"
        schedule_str = f"  {schedule}" if schedule else ""
        last_str = f"  last: {last_run}" if last_run else ""
        print(f"  {status_mark} [{tid}] {desc}  ({executor}{schedule_str}{last_str})")

    print()
    print(f"  {len(tasks)} task(s) — manage with /cron in-session")
    print()
