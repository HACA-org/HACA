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
from typing import TYPE_CHECKING, Any

from ..store import API_KEY_ENV, atomic_write, read_json, save_api_key
from .. import ui
from .ui import print_boot_header

if TYPE_CHECKING:
    from ..store import Layout


# ---------------------------------------------------------------------------
# Normal boot + session loop
# ---------------------------------------------------------------------------

def run_normal(layout: "Layout", workspace_focus: Path | None = None) -> None:
    from ..boot import run as boot_run, BootError
    from ..cpe.base import load_cpe_adapter_from_baseline
    from ..fap import FAPError
    from ..operator import present_evolution_proposals
    from ..session import run_session
    from ..sleep import run_sleep_cycle
    from ..store import atomic_write

    # Auto-set workspace_focus to cwd if provided and not already set to something else
    if workspace_focus is not None:
        focus_path = workspace_focus.resolve()
        # Only set if focus is outside entity root (safety check)
        try:
            focus_path.relative_to(layout.root)
        except ValueError:
            # Good — focus is outside entity root, safe to set
            if not layout.workspace_focus.exists():
                atomic_write(layout.workspace_focus, {"path": str(focus_path)})

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

def run_update(dry_run: bool = False) -> None:
    import hashlib
    import shutil
    import json as _json
    import tarfile
    import tempfile
    import urllib.request

    cli_file = Path(__file__).resolve()
    fcp_ref_root = cli_file.parents[2]   # cli/ -> fcp_base/ -> fcp-ref/

    # Guard: reject if running from within an entity root
    for ancestor in cli_file.parents:
        if (ancestor / ".fcp-entity").exists():
            ui.print_err("fcp update must be run from the global fcp installation.")
            ui.print_err("Use the 'fcp' command in your PATH, not a local copy.")
            sys.exit(1)
        if ancestor == fcp_ref_root:
            break

    def _sha256(path: Path) -> str:
        h = hashlib.sha256()
        h.update(path.read_bytes())
        return h.hexdigest()

    def _diff_dir_merge(src: Path, dst: Path) -> list[str]:
        """Return list of relative paths that differ between src/ and dst/."""
        changed = []
        for item in src.rglob("*"):
            if item.suffix in (".pyc", ".pyo") or "__pycache__" in item.parts:
                continue
            if item.is_dir():
                continue
            rel = item.relative_to(src)
            dst_item = dst / rel
            if not dst_item.exists() or _sha256(item) != _sha256(dst_item):
                changed.append(str(rel))
        return changed

    def _copy_dir_merge(src: Path, dst: Path) -> list[str]:
        """Copy src/ into dst/, overwriting matching files. Returns list of updated names."""
        updated = _diff_dir_merge(src, dst)
        dst.mkdir(parents=True, exist_ok=True)
        for rel in updated:
            src_item = src / rel
            dst_item = dst / rel
            dst_item.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_item, dst_item)
        return updated

    dry_tag = "  [dry-run]" if dry_run else ""

    # ── Step 1: Download latest fcp-ref ─────────────────────────────────────
    title = "fcp update --dry-run" if dry_run else "fcp update"
    ui.hr(title)
    ui.print_info("Downloading latest fcp-ref from github.com/HACA-org/HACA ...")
    print()

    tarball_url = "https://github.com/HACA-org/HACA/archive/refs/heads/main.tar.gz"
    _INNER = ("HACA-main", "implementations", "fcp-ref")

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            tarball = tmp_path / "haca-main.tar.gz"

            with urllib.request.urlopen(tarball_url, timeout=30) as resp:
                tarball.write_bytes(resp.read())

            prefix = "/".join(_INNER) + "/"
            with tarfile.open(tarball, "r:gz") as tf:
                members = [m for m in tf.getmembers() if m.name.startswith(prefix)]
                if not members:
                    ui.print_err("fcp-ref not found in downloaded archive.")
                    sys.exit(1)
                tf.extractall(tmp_path, members=members)

            new_fcp_ref = tmp_path.joinpath(*_INNER)

            from .init import read_fcp_version
            new_version = read_fcp_version(new_fcp_ref)

            # ── Step 2: Update CLI in-place ──────────────────────────────────
            if dry_run:
                ui.print_info(f"  CLI would be updated to v{new_version}{dry_tag}")
            else:
                for item in new_fcp_ref.iterdir():
                    dst = fcp_ref_root / item.name
                    if item.is_dir():
                        if dst.exists():
                            shutil.rmtree(dst)
                        shutil.copytree(item, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
                    else:
                        shutil.copy2(item, dst)
                fcp_exe = fcp_ref_root / "fcp"
                if fcp_exe.exists():
                    fcp_exe.chmod(0o755)
                ui.print_ok(f"CLI updated to v{new_version}.")
            print()

            # ── Step 3: Check installed entities ────────────────────────────
            from ..store import list_entities, entity_root_for
            entities = list_entities()

            if not entities:
                ui.print_info("No entities installed.")
                print()
                return

            ui.hr("Entities")
            print()

            outdated: list[tuple[str, str]] = []
            for eid in entities:
                eroot = entity_root_for(eid)
                try:
                    marker = _json.loads((eroot / ".fcp-entity").read_text(encoding="utf-8"))
                    ev = marker.get("version", "unknown")
                except Exception:
                    ev = "unknown"
                if ev == new_version:
                    ui.print_info(f"  {eid}  v{ev}  [up to date]")
                else:
                    ui.print_info(f"  {eid}  v{ev} → v{new_version}")
                    outdated.append((eid, ev))
            print()

            if not outdated:
                ui.print_ok(f"All entities are on v{new_version}.")
                print()
                return

            if dry_run:
                ui.print_info(f"  {len(outdated)} entity(ies) would be offered update.{dry_tag}")
                print()
                return

            # ── Step 4: Per-entity update with confirmation ──────────────────
            for eid, ev in outdated:
                eroot = entity_root_for(eid)

                if not ui.confirm(f"Update '{eid}'  v{ev} → v{new_version}?", default=True):
                    ui.print_info(f"  Skipped.")
                    print()
                    continue

                print()

                # Auto: fcp_base/, boot.md
                for src, dst_name in [
                    (new_fcp_ref / "fcp_base", "fcp_base"),
                    (new_fcp_ref / "boot.md",  "boot.md"),
                ]:
                    if not src.exists():
                        continue
                    dst = eroot / dst_name
                    if src.is_dir():
                        if dst.exists():
                            shutil.rmtree(dst)
                        shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
                    else:
                        shutil.copy2(src, dst)
                    ui.print_info(f"  [↓] {dst_name}")

                # fcp launcher
                fcp_src = new_fcp_ref / "fcp"
                if fcp_src.exists():
                    fcp_dst = eroot / "fcp"
                    shutil.copy2(fcp_src, fcp_dst)
                    fcp_dst.chmod(0o755)
                    ui.print_info("  [↓] fcp")

                # skills/lib/: full replace
                skills_lib_src = new_fcp_ref / "skills" / "lib"
                skills_lib_dst = eroot / "skills" / "lib"
                if skills_lib_src.exists():
                    if skills_lib_dst.exists():
                        shutil.rmtree(skills_lib_dst)
                    shutil.copytree(skills_lib_src, skills_lib_dst,
                                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
                    ui.print_info("  [↓] skills/lib/")

                # hooks/: merge — only update files present in template
                hooks_src = new_fcp_ref / "hooks"
                hooks_dst = eroot / "hooks"
                if hooks_src.exists():
                    updated_hooks = _copy_dir_merge(hooks_src, hooks_dst)
                    if updated_hooks:
                        for h in updated_hooks:
                            ui.print_info(f"  [↓] hooks/{h}")
                    else:
                        ui.print_info("  [·] hooks/  (no changes)")

                # Bump version in .fcp-entity marker
                marker_path = eroot / ".fcp-entity"
                try:
                    marker = _json.loads(marker_path.read_text(encoding="utf-8"))
                except Exception:
                    marker = {}
                marker["version"] = new_version
                marker_path.write_text(_json.dumps(marker, indent=2), encoding="utf-8")

                print()
                ui.print_ok(f"'{eid}' updated to v{new_version}.")
                print()

    except Exception as exc:
        ui.print_err(f"Update failed: {exc}")
        sys.exit(1)

    ui.hr()
    print()


# ---------------------------------------------------------------------------
# Status — shared rendering helper
# ---------------------------------------------------------------------------

def _fmt_duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m {seconds % 60}s"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    return f"{h}h {m}m"


def _last_integrity_event(layout: "Layout", event_type: str) -> tuple[str, str]:
    """Return (ts_iso, session_id) of the last matching event in integrity.log, or ('', '')."""
    if not layout.integrity_log.exists():
        return "", ""
    ts_iso = ""
    sid = ""
    for line in layout.integrity_log.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
            raw = rec.get("data", "{}")
            data = json.loads(raw) if isinstance(raw, str) else raw
            if not isinstance(data, dict):
                continue
            if data.get("type") == event_type:
                ts_raw = data.get("ts") or rec.get("ts", "")
                # ts may be ms int or ISO string
                if isinstance(ts_raw, (int, float)) and ts_raw > 1e10:
                    import datetime as _dt
                    ts_iso = _dt.datetime.utcfromtimestamp(ts_raw / 1000).strftime("%Y-%m-%dT%H:%M:%SZ")
                else:
                    ts_iso = str(ts_raw)
                sid = data.get("session_id", "")
        except Exception:
            continue
    return ts_iso, sid


def _last_evolution_event(layout: "Layout") -> tuple[str, str, str, str]:
    """Return (status, operator, ts_iso, session_id) of the last evolution event."""
    if not layout.integrity_log.exists():
        return "", "", "", ""
    status = ""
    operator = ""
    ts_iso = ""
    sid = ""
    for line in layout.integrity_log.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
            raw = rec.get("data", "{}")
            data = json.loads(raw) if isinstance(raw, str) else raw
            if not isinstance(data, dict):
                continue
            etype = data.get("type", "")
            if etype == "EVOLUTION_AUTH":
                status = "approved"
                content = data.get("content", {})
                if isinstance(content, str):
                    try:
                        content = json.loads(content)
                    except Exception:
                        content = {}
                operator = content.get("operator", "") if isinstance(content, dict) else ""
                ts_raw = data.get("ts", "") or rec.get("ts", "")
                if isinstance(ts_raw, (int, float)) and ts_raw > 1e10:
                    import datetime as _dt
                    ts_iso = _dt.datetime.utcfromtimestamp(ts_raw / 1000).strftime("%Y-%m-%dT%H:%M:%SZ")
                else:
                    ts_iso = str(ts_raw)
                sid = data.get("session_id", "")
            elif etype == "EVOLUTION_REJECTED":
                status = "rejected"
                ts_raw = data.get("ts", "") or rec.get("ts", "")
                if isinstance(ts_raw, (int, float)) and ts_raw > 1e10:
                    import datetime as _dt
                    ts_iso = _dt.datetime.utcfromtimestamp(ts_raw / 1000).strftime("%Y-%m-%dT%H:%M:%SZ")
                else:
                    ts_iso = str(ts_raw)
                sid = ""
        except Exception:
            continue

    # check for pending proposals
    if layout.operator_notifications_dir.exists():
        for f in layout.operator_notifications_dir.iterdir():
            try:
                n = read_json(f)
                if n.get("type") == "evolution_proposal" or (
                    isinstance(n.get("detail"), dict) and n["detail"].get("type") == "EVOLUTION_PROPOSAL"
                ):
                    status = "pending"
                    break
            except Exception:
                continue

    return status, operator, ts_iso, sid


def _print_status_sections(layout: "Layout", beacon_is_active: Any, in_session: bool = False,
                            live_tokens: int = 0, live_ctx_window: int = 0,
                            live_budget_tokens: int = 0, live_cycle: int = 0) -> None:
    from pathlib import Path as _Path
    import datetime as _dt

    # --- ENTITY ---
    ui.hr("ENTITY")
    baseline: dict = {}
    try:
        baseline = read_json(layout.baseline)
        cpe = baseline.get("cpe", {})
        backend = cpe.get("backend", "?")
        model = cpe.get("model", "?")
        entity_version = baseline.get("fcp_version", "?")
        profile = baseline.get("profile", "?")

        try:
            from importlib.metadata import version as _ver
            fcp_version = _ver("fcp")
        except Exception:
            try:
                from .. import __version__ as fcp_version  # type: ignore
            except Exception:
                fcp_version = "?"

        if fcp_version != "?" and entity_version != "?" and entity_version != fcp_version:
            version_label = f"v{entity_version}  [!] fcp {fcp_version} available"
        else:
            version_label = f"v{entity_version}"

        imprint: dict = {}
        if layout.imprint.exists():
            try:
                imprint = read_json(layout.imprint)
            except Exception:
                pass
        op_bound = imprint.get("operator_bound", {})
        op_name = op_bound.get("operator_name", "(not enrolled)")
        op_email = op_bound.get("operator_email", "")
        op_str = f"{op_name} — {op_email}" if op_email else op_name
        activated_at = imprint.get("activated_at", "?")

        ui.print_info(f"FCP            : {version_label}")
        ui.print_info(f"Profile        : {profile}")
        ui.print_info(f"Path           : {layout.root}")
        ui.print_info(f"Operator       : {op_str}")
        ui.print_info(f"Activation     : {activated_at}")
    except Exception:
        ui.print_warn("baseline.json unreadable")
    print()

    # --- SESSION ---
    ui.hr("SESSION")
    token_active = layout.session_token.exists()
    ui.print_info(f"Token          : {'active' if token_active else 'inactive'}")

    # model + ctx
    try:
        cpe = baseline.get("cpe", {})
        backend = cpe.get("backend", "?")
        model = cpe.get("model", "?")
        from ..cpe.models import get_context_window
        ctx_window = get_context_window(backend, model)
        budget_pct = baseline.get("context_window", {}).get("budget_pct", 80)
        ctx_str = f"{ctx_window:,}" if ctx_window else "unknown"
        ui.print_info(f"Model          : {backend}:{model}")
        ui.print_info(f"  ctx          : {ctx_str}")
        ui.print_info(f"  budget       : {budget_pct}%")
        if in_session and live_tokens and ctx_window:
            ctx_pct = round(live_tokens / ctx_window * 100, 1)
            budget_used = round(live_tokens / live_budget_tokens * 100, 1) if live_budget_tokens else 0.0
            ui.print_info(f"  ctx used     : {ctx_pct}%  ({live_tokens:,} / {ctx_window:,})")
            ui.print_info(f"  budget used  : {budget_used}%  ({live_tokens:,} / {live_budget_tokens:,})")
            ui.print_info(f"  cycle        : {live_cycle}")
    except Exception:
        pass

    # last session info
    if layout.last_session.exists():
        try:
            ls = read_json(layout.last_session)
            ls_cycles = ls.get("cycles", 0)
            ls_dur = _fmt_duration(ls.get("duration_seconds", 0))
            ls_date = ls.get("closed_at", "?")
            ls_sid = ls.get("session_id", "?")
            ui.print_info(f"Last session   : {ls_cycles} cycles / {ls_dur} / {ls_date} / {ls_sid}")
            total_cycles = ls.get("total_cycles", 0)
            total_sessions = ls.get("total_sessions", 0)
            total_dur = _fmt_duration(ls.get("total_duration_seconds", 0))
            ui.print_info(f"Total          : {total_cycles} cycles / {total_sessions} sessions / {total_dur}")
        except Exception:
            pass

    # last closure payload
    cp_ts, cp_sid = _last_integrity_event(layout, "CLOSURE_PROCESSED")
    if cp_ts:
        ui.print_info(f"Last closure   : {cp_ts} / {cp_sid}" if cp_sid else f"Last closure   : {cp_ts}")

    # last sleep cycle
    sc_ts, sc_sid = _last_integrity_event(layout, "SLEEP_COMPLETE")
    if sc_ts:
        ui.print_info(f"Last sleep     : {sc_ts} / {sc_sid}" if sc_sid else f"Last sleep     : {sc_ts}")

    # last evolution proposal
    ev_status, ev_op, ev_ts, ev_sid = _last_evolution_event(layout)
    if ev_status:
        ev_parts = [ev_status]
        if ev_op:
            ev_parts.append(ev_op)
        if ev_ts:
            ev_parts.append(ev_ts)
        if ev_sid:
            ev_parts.append(ev_sid)
        ev_str = " / ".join(ev_parts)
        if ev_status == "pending":
            ui.print_warn(f"Last evolution : {ev_str}")
        else:
            ui.print_info(f"Last evolution : {ev_str}")

    # last heartbeat
    from ..exec_.counters import last_heartbeat_ts
    hb_ts = last_heartbeat_ts(layout)
    if hb_ts:
        hb_str = _dt.datetime.utcfromtimestamp(hb_ts).strftime("%Y-%m-%dT%H:%M:%SZ")
        ui.print_info(f"Last heartbeat : {hb_str}")
    print()

    # --- STATE ---
    ui.hr("STATE")
    if beacon_is_active(layout):
        ui.print_warn("Beacon         : ACTIVE")
    else:
        ui.print_info("Beacon         : clear")

    agenda_count = 0
    if layout.agenda.exists():
        try:
            agenda_count = len(read_json(layout.agenda).get("tasks", []))
        except Exception:
            pass
    ui.print_info(f"Agenda         : {agenda_count} task(s)")

    ep_count = 0
    sem_count = 0
    for subdir in ("episodic", "semantic"):
        d = layout.root / "memory" / subdir
        if d.exists():
            n = sum(1 for _ in d.iterdir() if _.is_file())
            if subdir == "episodic":
                ep_count = n
            else:
                sem_count = n
    mem_count = ep_count + sem_count
    ui.print_info(f"Memories       : {mem_count}  ({ep_count} episodic / {sem_count} semantic)")

    wf = ""
    if layout.workspace_focus.exists():
        try:
            wf = str(read_json(layout.workspace_focus).get("path", ""))
        except Exception:
            pass
    ui.print_info(f"Workspace      : {wf or '(not set)'}")

    # CMI status
    cmi_active = False
    try:
        cmi_cfg = baseline.get("cmi", {})
        cmi_active = bool(cmi_cfg.get("active"))
    except Exception:
        pass
    ui.print_info(f"CMI            : {'active' if cmi_active else 'inactive'}")

    # MCP / pairing
    pairing_dir = _Path.home() / ".fcp" / "pairing"
    pairing_active = pairing_dir.exists() and bool(list(pairing_dir.glob("*.meta.json")))
    ui.print_info(f"MCP            : {'active' if pairing_active else 'inactive'}")

    # inbox
    inbox_count = 0
    if layout.inbox_dir.exists():
        inbox_count = sum(1 for f in layout.inbox_dir.iterdir() if f.is_file())
    if inbox_count:
        ui.print_warn(f"[!] /inbox     : {inbox_count} pending")
    print()

    # --- PAIRING (detail) ---
    if pairing_active:
        ui.hr("PAIRING")
        for meta_path in pairing_dir.glob("*.meta.json"):
            try:
                meta = read_json(meta_path)
                sid = meta.get("session_id", "?")
                key = meta.get("key", "?")
                model_p = meta.get("model", "?")
                started = meta.get("started_at", "?")
                request_path = pairing_dir / f"{sid}.request.json"
                pending = "yes" if request_path.exists() else "no"
                ui.print_info(f"Session        : {sid}  key: {key}")
                ui.print_info(f"Model          : {model_p}")
                ui.print_info(f"Started        : {started}")
                ui.print_info(f"MCP dir        : {pairing_dir}")
                ui.print_info(f"Pending prompt : {pending}")
            except Exception:
                pass
        print()


# ---------------------------------------------------------------------------
# Status — entity overview without booting a session
# ---------------------------------------------------------------------------

def run_status(layout: "Layout") -> None:
    """Print entity status overview (no session required)."""
    from ..sil import beacon_is_active
    from pathlib import Path as _Path

    ui.hr("fcp status")
    _print_status_sections(layout, beacon_is_active, in_session=False)


# ---------------------------------------------------------------------------
# Agenda — list scheduled tasks without booting a session
# ---------------------------------------------------------------------------

def run_agenda(layout: "Layout") -> None:
    """List scheduled tasks from agenda.json (no session required)."""
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
