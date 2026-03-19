"""
Operator Interface — FCP §12.

§12.2  Interactive loop (input → inject as MSG → session cycle)
§12.3.1 Platform commands (/status, /doctor, /model, /endure, /inbox, /work, /skill, /verbose, /debugger)
§12.3.2 Skill aliases (/commit, ...)
§12.4  Notifications
"""

from __future__ import annotations

import itertools
import json
import os
import time
from pathlib import Path
from typing import Any

from .acp import make as acp_encode
from .sil import sha256_str as _sha256_str, write_evolution_auth as _write_evolution_auth
from .store import Layout, append_jsonl, atomic_write, load_agenda, read_json
from . import ui


# ---------------------------------------------------------------------------
# Debug state — session-scoped, not persisted
# ---------------------------------------------------------------------------

_verbose: bool = False
_debugger: str | None = None  # None | "all" | "chat" | "boot"
_compact_pending: bool = False
_endure_approved: bool = False


def is_verbose() -> bool:
    return _verbose


def set_verbose(value: bool) -> None:
    global _verbose
    _verbose = value


def get_debugger() -> str | None:
    return _debugger


def set_debugger(mode: str | None) -> None:
    global _debugger
    _debugger = mode


def is_compact_pending() -> bool:
    return _compact_pending


def set_compact_pending(value: bool) -> None:
    global _compact_pending
    _compact_pending = value


def is_endure_approved() -> bool:
    return _endure_approved


def set_endure_approved(value: bool) -> None:
    global _endure_approved
    _endure_approved = value


# ---------------------------------------------------------------------------
# Notifications  §12.4
# ---------------------------------------------------------------------------

def present_notifications(layout: Layout) -> None:
    """Print pending operator notifications."""
    if not layout.operator_notifications_dir.exists():
        return
    for f in sorted(layout.operator_notifications_dir.iterdir()):
        if f.suffix in (".json",) and not f.name.endswith(".tmp"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                inner = data.get("data", data)
                ntype = inner.get("type", "NOTIFICATION") if isinstance(inner, dict) else "NOTIFICATION"
                print(f"\n[{ntype}] {json.dumps(inner, indent=2)}")
            except Exception:
                pass


def present_evolution_proposals(layout: Layout) -> list[dict[str, Any]]:
    """Display pending Evolution Proposals and collect Operator decisions."""
    if not layout.operator_notifications_dir.exists():
        return []

    proposals: list[dict[str, Any]] = []
    for f in sorted(layout.operator_notifications_dir.iterdir()):
        if "proposal_pending" in f.name and f.suffix == ".json":
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                inner = data.get("data", data)
                if isinstance(inner, str):
                    try:
                        inner = json.loads(inner)
                    except Exception:
                        inner = {}
                if isinstance(inner, dict) and inner.get("type") == "PROPOSAL_PENDING":
                    proposals.append({"file": f, "data": inner})
            except Exception:
                pass

    authorized: list[dict[str, Any]] = []
    for p in proposals:
        inner = p["data"]
        content = inner.get("content", "")
        print(f"\n[EVOLUTION PROPOSAL]\n{content}\n")
        answer = "y" if ui.confirm("Approve?", default=False) else "n"
        if answer == "y":
            auth_digest = _sha256_str(content)
            authorized.append({
                "seq": inner.get("ts", int(time.time() * 1000)),
                "content": content,
                "auth_digest": auth_digest,
                "slugs": inner.get("slugs", []),
            })
            _write_evolution_auth(layout, content, auth_digest)
            from .stimuli import inject_evolution_result
            inject_evolution_result(layout, content, approved=True)
        else:
            _write_evolution_rejected(layout, content)
            from .stimuli import inject_evolution_result
            inject_evolution_result(layout, content, approved=False)
        pfile = p["file"]
        if isinstance(pfile, Path):
            pfile.unlink(missing_ok=True)

    return authorized


# ---------------------------------------------------------------------------
# Platform commands  §12.3.1
# ---------------------------------------------------------------------------

_CMD_INDENT = "    "  # 4 spaces


class _DimWriter:
    """Wraps sys.stdout to prefix each line with indent + dim colour."""
    def __init__(self, orig):
        self._orig = orig

    def write(self, text: str) -> int:
        if text == "\n":
            self._orig.write("\n")
        else:
            lines = text.split("\n")
            out = "\n".join(
                f"{ui.DIM}{_CMD_INDENT}{l}{ui.RESET}" if l else l
                for l in lines
            )
            self._orig.write(out)
        return len(text)

    def flush(self) -> None:
        self._orig.flush()

    def __getattr__(self, name: str):
        return getattr(self._orig, name)


import contextlib as _contextlib

@_contextlib.contextmanager
def _cmd_output():
    import sys as _sys
    orig = _sys.stdout
    _sys.stdout = _DimWriter(orig)
    try:
        yield
    finally:
        _sys.stdout = orig


def handle_platform_command(layout: Layout, line: str, adapter_ref: Any = None) -> bool:
    """Handle a /command line. Returns True if handled, False if unknown."""
    parts = line.strip().split()
    if not parts:
        return False
    cmd = parts[0].lower()
    args = list(itertools.islice(parts, 1, len(parts)))

    with _cmd_output():
        return _dispatch_command(layout, cmd, args, adapter_ref)
    return False  # unreachable; satisfies type checker


def _dispatch_command(layout: Layout, cmd: str, args: list, adapter_ref: Any) -> bool:
    # --- Entity & session ---
    if cmd == "/status":
        _cmd_status(layout)
        return True
    if cmd == "/doctor":
        _cmd_doctor(layout, args)
        return True
    if cmd in ("/exit", "/bye", "/close"):
        print("  closing session...")
        return True
    if cmd in ("/new", "/clear", "/reset"):
        print("  resetting session...")
        if layout.session_store.exists():
            layout.session_store.write_text("", encoding="utf-8")
        return True

    # --- Memory & inbox ---
    if cmd == "/memory":
        _cmd_memory(layout, args)
        return True
    if cmd == "/inbox":
        _cmd_inbox(layout, args)
        return True

    # --- Workspace ---
    if cmd == "/work":
        _cmd_work(layout, args)
        return True

    # --- Skills & execution ---
    if cmd in ("/skill", "/skills"):
        _cmd_skill(layout, args)
        return True
    if cmd in ("/shell", "/allowlist"):
        _cmd_allowlist(layout, args)
        return True

    # --- Model, endure & cron ---
    if cmd == "/model":
        _cmd_model(layout, args, adapter_ref)
        return True
    if cmd == "/endure":
        _cmd_endure(layout, args)
        return True
    if cmd == "/cron":
        _cmd_cron(layout, args)
        return True
    if cmd == "/cmi":
        _cmd_cmi(layout, args)
        return True

    # --- Compact ---
    if cmd == "/compact":
        _cmd_compact()
        return True

    # --- Debug ---
    if cmd == "/verbose":
        _cmd_verbose(layout, args)
        return True
    if cmd == "/debugger":
        _cmd_debugger(layout, args)
        return True

    if cmd == "/help":
        _cmd_help()
        return True

    return False


# --- Entity & session ---

def _cmd_status(layout: Layout) -> None:
    token_present = layout.session_token.exists()
    session_size = layout.session_store.stat().st_size if layout.session_store.exists() else 0
    beacon = layout.distress_beacon.exists()
    print(f"  session token  : {'active' if token_present else 'inactive'}")
    print(f"  session store  : {session_size} bytes")
    print(f"  distress beacon: {'ACTIVE' if beacon else 'clear'}")
    wf = ""
    if layout.workspace_focus.exists():
        try:
            wf = str(read_json(layout.workspace_focus).get("path", ""))
        except Exception:
            pass
    print(f"  workspace focus: {wf or '(not set)'}")


def run_doctor(layout: Layout, fix: bool, clear_sentinels: bool = False) -> None:
    """Core doctor logic — shared by /doctor (in-session) and ./fcp doctor (CLI).

    Args:
        fix: repair volatile dirs and recalculate integrity hashes.
        clear_sentinels: also clear distress beacon and stale session token (CLI only).
    """
    from .compliance import run_all, print_report
    from .sil import beacon_is_active, clear_beacon

    if fix:
        if clear_sentinels:
            if beacon_is_active(layout):
                clear_beacon(layout)
                print("  distress beacon cleared")
            if layout.session_token.exists():
                layout.session_token.unlink()
                print("  stale session token removed")

        for d in layout.volatile_dirs():
            if not d.exists():
                d.mkdir(parents=True, exist_ok=True)
                print(f"  created: {d.relative_to(layout.root)}")
        fix_integrity_hashes(layout)

    findings = run_all(layout)
    print_report(findings)
    failed = [f for f in findings if not f.passed]
    if failed:
        hint = "./fcp doctor --fix" if clear_sentinels else "/doctor --fix"
        print(f"\n  {len(failed)} issue(s) found. Run {hint} to repair.")


def _cmd_doctor(layout: Layout, args: list[str]) -> None:
    run_doctor(layout, fix="--fix" in args, clear_sentinels=False)


def fix_integrity_hashes(layout: Layout) -> None:
    """Recalculate sha256 hashes for all files tracked in integrity.json."""
    import hashlib
    if not layout.integrity_doc.exists():
        return
    try:
        doc = read_json(layout.integrity_doc)
    except Exception:
        return
    files: dict[str, str] = doc.get("files", {})
    updated = 0
    for rel in list(files.keys()):
        p = layout.root / rel
        if p.exists() and p.is_file():
            digest = hashlib.sha256(p.read_bytes()).hexdigest()
            new_val = f"sha256:{digest}"
            if files[rel] != new_val:
                files[rel] = new_val
                updated += 1
    if updated:
        doc["files"] = files
        atomic_write(layout.integrity_doc, doc)
        print(f"  integrity.json: updated {updated} hash(es)")
    else:
        print("  integrity.json: all hashes up to date")


# --- Memory & inbox ---

def _cmd_memory(layout: Layout, args: list[str]) -> None:
    query = args[0].lower() if args else ""
    found = False
    for subdir in ("episodic", "semantic"):
        d = layout.memory_dir / subdir
        if not d.exists():
            continue
        files = sorted(f for f in d.rglob("*.md") if not query or query in f.name.lower())
        if files:
            print(f"  {subdir}/")
            for f in files:
                print(f"    {f.relative_to(layout.memory_dir)}")
            found = True
    if not found:
        print("  memory store empty" if not query else f"  no results for '{query}'")


def _cmd_inbox(layout: Layout, args: list[str]) -> None:
    if not args:
        print("  usage: /inbox list | view <id> | dismiss <id> | clear")
        return
    sub = args[0].lower()
    if sub == "list":
        _inbox_list(layout)
    elif sub == "view" and len(args) > 1:
        _inbox_view(layout, args[1])
    elif sub == "dismiss" and len(args) > 1:
        _inbox_dismiss(layout, args[1])
    elif sub == "clear":
        _inbox_clear(layout)
    else:
        print("  usage: /inbox list | view <id> | dismiss <id> | clear")


def _inbox_notifications(layout: Layout) -> list[Path]:
    """Return sorted notification files excluding proposal_pending."""
    if not layout.operator_notifications_dir.exists():
        return []
    return [
        f for f in sorted(layout.operator_notifications_dir.iterdir())
        if f.suffix == ".json" and not f.name.endswith(".tmp")
        and "proposal_pending" not in f.name
    ]


def _inbox_list(layout: Layout) -> None:
    files = _inbox_notifications(layout)
    if not files:
        print("  inbox empty")
        return
    for i, f in enumerate(files):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            inner = data.get("data", data)
            ntype = inner.get("type", "?") if isinstance(inner, dict) else "?"
            print(f"  [{i}] {ntype}  {f.name}")
        except Exception:
            print(f"  [{i}] (unreadable)  {f.name}")


def _inbox_view(layout: Layout, idx_str: str) -> None:
    files = _inbox_notifications(layout)
    try:
        idx = int(idx_str)
        f = files[idx]
    except (ValueError, IndexError):
        print(f"  no notification at index {idx_str}")
        return
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        print(json.dumps(data.get("data", data), indent=2, ensure_ascii=False))
    except Exception as exc:
        print(f"  could not read: {exc}")


def _inbox_dismiss(layout: Layout, idx_str: str) -> None:
    files = _inbox_notifications(layout)
    try:
        idx = int(idx_str)
        f = files[idx]
    except (ValueError, IndexError):
        print(f"  no notification at index {idx_str}")
        return
    f.unlink(missing_ok=True)
    print(f"  dismissed: {f.name}")


def _inbox_clear(layout: Layout) -> None:
    files = _inbox_notifications(layout)
    if not files:
        print("  inbox already empty")
        return
    for f in files:
        f.unlink(missing_ok=True)
    print(f"  cleared {len(files)} notification(s)")


# --- Workspace ---

def _cmd_work(layout: Layout, args: list[str]) -> None:
    if not args:
        print("  usage: /work set <subdir> | clone <repo> | status | clear")
        return
    sub = args[0].lower()
    if sub == "set" and len(args) > 1:
        subdir = args[1]
        try:
            profile = read_json(layout.baseline).get("profile", "haca-core")
        except Exception:
            profile = "haca-core"
        boundary = layout.root if profile == "haca-evolve" else layout.workspace_dir
        target = (boundary / subdir).resolve() if subdir not in (".", "") else boundary.resolve()
        try:
            target.relative_to(boundary)
        except ValueError:
            print(f"  path outside {'entity root' if profile == 'haca-evolve' else 'workspace'}: {subdir}")
            return
        if not target.exists():
            target.mkdir(parents=True)
            print(f"  created: {target}")
        if layout.workspace_focus.exists():
            try:
                current = str(read_json(layout.workspace_focus).get("path", ""))
            except Exception:
                current = ""
            if current:
                if not ui.confirm(f"workspace focus already set to {current!r}. Overwrite?", default=False):
                    ui.print_info("aborted.")
                    return
        atomic_write(layout.workspace_focus, {"path": str(target)})
        print(f"  workspace focus set: {target}")
    elif sub == "clone" and len(args) > 1:
        import subprocess
        repo = args[1]
        name = repo.rstrip("/").split("/")[-1].removesuffix(".git")
        dest = layout.workspace_dir / name
        r = subprocess.run(["git", "clone", repo, str(dest)], capture_output=True, text=True)
        if r.returncode != 0:
            print(f"  clone failed: {r.stderr.strip()}")
            return
        atomic_write(layout.workspace_focus, {"path": str(dest)})
        print(f"  cloned and focus set: {dest}")
    elif sub == "status":
        wf = ""
        if layout.workspace_focus.exists():
            try:
                wf = str(read_json(layout.workspace_focus).get("path", ""))
            except Exception:
                pass
        print(f"  workspace focus: {wf or '(not set)'}")
        if layout.workspace_dir.exists():
            subdirs = [d for d in sorted(layout.workspace_dir.iterdir()) if d.is_dir()]
            if subdirs:
                print("  available:")
                for d in subdirs:
                    print(f"    {d.name}")
    elif sub == "clear":
        if layout.workspace_focus.exists():
            layout.workspace_focus.unlink()
            print("  workspace focus cleared")
        else:
            print("  workspace focus not set")
    else:
        print("  usage: /work set <subdir> | clone <repo> | status | clear")


# --- Skills & execution ---

def _cmd_allowlist(layout: Layout, args: list[str]) -> None:
    """Manage shell_run allowlist_composite entries."""
    manifest_path = layout.skills_lib_dir / "shell_run" / "manifest.json"
    if not manifest_path.exists():
        print("  shell_run skill not found")
        return

    def _load() -> dict:
        try:
            return read_json(manifest_path)
        except Exception as exc:
            print(f"  error reading manifest: {exc}")
            return {}

    def _save(manifest: dict) -> None:
        import os
        tmp = manifest_path.with_suffix(".json.tmp")
        import json as _json
        tmp.write_text(_json.dumps(manifest, indent=2), encoding="utf-8")
        os.replace(tmp, manifest_path)

    if not args or args[0] == "list":
        manifest = _load()
        simple = manifest.get("allowlist", [])
        composite = manifest.get("allowlist_composite", [])
        print("  simple allowlist:")
        for cmd in simple:
            print(f"    {cmd}")
        print("  composite allowlist:")
        if composite:
            for i, e in enumerate(composite):
                label = f"  [{e['label']}]" if e.get("label") else ""
                print(f"    [{i}] {e['command']}{label}")
        else:
            print("    (empty)")
        return

    sub = args[0].lower()

    if sub == "allow":
        # /allowlist allow <command> [label]
        if len(args) < 2:
            print("  usage: /allowlist allow <command> [label]")
            return
        command = args[1]
        label = args[2] if len(args) > 2 else ""
        manifest = _load()
        if not manifest:
            return
        composite: list = manifest.get("allowlist_composite", [])
        if any(e.get("command") == command for e in composite):
            print(f"  already in allowlist_composite: {command!r}")
            return
        entry: dict = {"command": command}
        if label:
            entry["label"] = label
        composite.append(entry)
        manifest["allowlist_composite"] = composite
        _save(manifest)
        print(f"  added: {command!r}")
        return

    if sub == "remove":
        # /allowlist remove <index|label|command>
        if len(args) < 2:
            print("  usage: /allowlist remove <index | label | command>")
            return
        key = args[1]
        manifest = _load()
        if not manifest:
            return
        composite = manifest.get("allowlist_composite", [])
        original_len = len(composite)
        # try index first
        try:
            idx = int(key)
            if 0 <= idx < len(composite):
                removed = composite.pop(idx)
                manifest["allowlist_composite"] = composite
                _save(manifest)
                print(f"  removed [{idx}]: {removed['command']!r}")
                return
        except ValueError:
            pass
        # try label or command match
        new_composite = [e for e in composite if e.get("label") != key and e.get("command") != key]
        if len(new_composite) == original_len:
            print(f"  not found: {key!r}")
            return
        manifest["allowlist_composite"] = new_composite
        _save(manifest)
        print(f"  removed entries matching {key!r}")
        return

    print("  usage: /allowlist list | allow <command> [label] | remove <index|label|command>")


def _skill_run_direct(layout: Layout, skill_name: str, params: dict[str, Any]) -> None:
    """Run a skill directly from the operator prompt and print output."""
    from .exec_ import dispatch, ExecError, SkillRejected
    if not layout.skills_index.exists():
        ui.print_err("skills/index.json not found")
        return
    idx = read_json(layout.skills_index) or {}
    skill_names = [s["name"] for s in idx.get("skills", [])]
    if skill_name not in skill_names:
        ui.print_err(f"skill not found: {skill_name!r}")
        print(f"  available: {', '.join(skill_names)}")
        return
    try:
        output = dispatch(layout, skill_name, params, idx)
        print()
        ui.hr(f"skill: {skill_name}")
        print(output)
        print()
    except SkillRejected as exc:
        ui.print_warn(f"skill rejected: {exc}")
    except ExecError as exc:
        ui.print_err(f"exec error: {exc}")


def _cmd_skill(layout: Layout, args: list[str]) -> None:
    if not args:
        print("  usage: /skill list | add | run <name> [k=v ...] | audit <name>")
        return
    sub = args[0].lower()
    if sub == "list":
        if layout.skills_index.exists():
            idx = read_json(layout.skills_index)
            for s in idx.get("skills", []):
                print(f"  {s['name']} [{s.get('class', '?')}]")
        else:
            print("  skills/index.json not found")
    elif sub == "add":
        print("  /skill add requires an active session — use the skill_create tool during a session.")
    elif sub == "run" and len(args) > 1:
        skill_name = args[1]
        # Parse optional key=value params from remaining args
        params: dict[str, Any] = {}
        for token in args[2:]:
            if "=" in token:
                k, _, v = token.partition("=")
                params[k.strip()] = v.strip()
        _skill_run_direct(layout, skill_name, params)
    elif sub == "audit" and len(args) > 1:
        print(f"  audit {args[1]}: use /skill audit via EXEC dispatch during session")
    else:
        print("  usage: /skill list | add | run <name> [k=v ...] | audit <name>")


# --- Model & endure ---

def _cmd_model(layout: Layout, args: list[str], adapter_ref: Any = None) -> None:
    try:
        baseline = read_json(layout.baseline)
        cpe_cfg = baseline.get("cpe", {})
    except Exception:
        print("  could not read baseline")
        return

    current_backend = cpe_cfg.get("backend", "ollama")
    current_model = cpe_cfg.get("model", "")

    # /model and /model list both open the interactive picker
    selected = _pick_model_interactive(current_backend, current_model)
    if selected is None:
        return
    backend, new_model = selected
    if backend == current_backend and new_model == current_model:
        print(f"  no change ({current_backend}:{current_model})")
        return
    if adapter_ref is None:
        print("  /model is only available during an active session")
        return
    from .cpe.base import make_adapter
    from .store import API_KEY_ENV, save_api_key, load_env_file
    
    api_key = ""
    if backend != "ollama":
        env_var = API_KEY_ENV.get(backend, "")
        api_key = os.environ.get(env_var, "")
        if not api_key:
            # Fallback if somehow chosen but no key in env
            api_key = ui.ask(f"{env_var} [not configured]")
            if api_key:
                save_api_key(layout.root.name, env_var, api_key)

    try:
        new_adapter = make_adapter(backend=backend, model=new_model, api_key=api_key)
    except Exception as exc:
        print(f"  failed to create adapter: {exc}")
        return
    adapter_ref.current = new_adapter
    cpe_cfg["backend"] = backend
    cpe_cfg["model"] = new_model
    baseline["cpe"] = cpe_cfg
    from .store import atomic_write
    atomic_write(layout.baseline, baseline)
    print(f"  switched → {backend}:{new_model}")


def _pick_model_interactive(current_backend: str, current_model: str) -> tuple[str, str] | None:
    """Interactive arrow-key picker organised by provider. Returns (backend, model) or None."""
    from .cpe.base import KNOWN_MODELS, BACKENDS, fetch_ollama_models
    from .store import API_KEY_ENV

    labels: list[str] = []
    pairs: list[tuple[str, str]] = []

    for backend in BACKENDS:
        if backend != "ollama":
            env_var = API_KEY_ENV.get(backend, "")
            if not os.environ.get(env_var):
                continue
        models = fetch_ollama_models() if backend == "ollama" else KNOWN_MODELS.get(backend, [])
        for m in models:
            active = backend == current_backend and m == current_model
            label = f"{backend}:{m} ✓" if active else f"{backend}:{m}"
            labels.append(label)
            pairs.append((backend, m))

    if not labels:
        ui.print_info("no models available")
        return None

    sel_idx = next(
        (i for i, (b, m) in enumerate(pairs) if b == current_backend and m == current_model),
        0,
    )

    try:
        chosen = ui.pick_one("Select model", labels, default_idx=sel_idx, indent="  ")
    except KeyboardInterrupt:
        return None

    chosen_idx = next(i for i, lbl in enumerate(labels) if lbl == chosen)
    return pairs[chosen_idx]


def print_integrity_chain(layout: Layout) -> None:
    """Display all entries in the integrity chain."""
    from .store import read_jsonl
    print()
    ui.hr("integrity chain")
    if not layout.integrity_chain.exists() or layout.integrity_chain.stat().st_size == 0:
        ui.print_info("Integrity chain is empty.")
        print()
        return
    entries = read_jsonl(layout.integrity_chain)
    if not entries:
        ui.print_info("Integrity chain is empty.")
        print()
        return
    for entry in entries:
        seq = entry.get("seq", "?")
        etype = entry.get("type", "?")
        ts = entry.get("ts", "")
        prev = entry.get("prev_hash", "")
        auth = entry.get("evolution_auth_digest", "")
        imprint = entry.get("imprint_hash", "")
        type_color = "\x1b[96m" if etype == "GENESIS" else (
            "\x1b[92m" if etype == "ENDURE_COMMIT" else "\x1b[93m"
        )
        print(f"  {ui.DIM}#{seq:>4}{ui.RESET}  {type_color}{etype:<20}{ui.RESET}  {ui.DIM}{ts}{ui.RESET}")
        if imprint:
            print(f"         imprint  {ui.DIM}{imprint[:72]}{ui.RESET}")
        if prev:
            print(f"         prev     {ui.DIM}{prev[:72]}{ui.RESET}")
        if auth:
            print(f"         auth     {ui.DIM}{auth[:72]}{ui.RESET}")
    print()
    print(f"  {len(entries)} entr{'y' if len(entries) == 1 else 'ies'} total")
    print()


def _cmd_endure(layout: Layout, args: list[str]) -> None:
    if not args:
        print("  usage: /endure list | approve <id> | reject <id> | chain")
        return
    sub = args[0].lower()
    if sub == "list":
        _endure_list(layout)
    elif sub == "approve" and len(args) > 1:
        _endure_decide(layout, args[1], approve=True)
    elif sub == "reject" and len(args) > 1:
        _endure_decide(layout, args[1], approve=False)
    elif sub == "chain":
        print_integrity_chain(layout)
    else:
        print("  usage: /endure list | approve <id> | reject <id> | chain")


def _endure_proposals(layout: Layout) -> list[dict]:
    """Return list of pending proposal dicts with 'file' and 'data' keys."""
    if not layout.operator_notifications_dir.exists():
        return []
    proposals = []
    for f in sorted(layout.operator_notifications_dir.iterdir()):
        if "proposal_pending" in f.name and f.suffix == ".json":
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                inner = data.get("data", {})
                if isinstance(inner, str):
                    try:
                        inner = json.loads(inner)
                    except Exception:
                        inner = {}
                if isinstance(inner, dict) and inner.get("type") == "PROPOSAL_PENDING":
                    proposals.append({"file": f, "data": inner})
            except Exception:
                pass
    return proposals


def _endure_list(layout: Layout) -> None:
    proposals = _endure_proposals(layout)
    if not proposals:
        print("  no pending proposals")
        return
    for i, p in enumerate(proposals):
        content = str(p["data"].get("content", ""))
        preview = content[:80] + ("..." if len(content) > 80 else "")
        print(f"  [{i}] {preview}")


def _endure_decide(layout: Layout, idx_str: str, approve: bool) -> None:
    proposals = _endure_proposals(layout)
    try:
        idx = int(idx_str)
        p = proposals[idx]
    except (ValueError, IndexError):
        print(f"  no proposal at index {idx_str}")
        return
    inner = p["data"]
    content = str(inner.get("content", ""))
    if approve:
        auth_digest = _sha256_str(content)
        _write_evolution_auth(layout, content, auth_digest)
        from .stimuli import inject_evolution_result
        inject_evolution_result(layout, content, approved=True)
        print(f"  approved: [{idx}] — session will close for Sleep Cycle and reboot")
        set_endure_approved(True)
        from .hooks import run_hook
        run_hook(layout, "on_evolution_authorized", {"content": content[:256], "auth_digest": auth_digest})
    else:
        _write_evolution_rejected(layout, content)
        _write_evolution_stimuli(layout, content, approved=False)
        print(f"  rejected: [{idx}]")
        from .hooks import run_hook
        run_hook(layout, "on_evolution_rejected", {"content": content[:256]})
    pfile = p["file"]
    if isinstance(pfile, Path):
        pfile.unlink(missing_ok=True)




# --- Cron ---

def _cmd_cron(layout: Layout, args: list[str]) -> None:
    if not args:
        print("  usage: /cron list | add | approve <id> | reject <id> | remove <id> [--all]")
        return
    sub = args[0].lower()
    if sub == "list":
        _cron_list(layout)
    elif sub == "add":
        _cron_add_interactive(layout)
    elif sub == "approve" and len(args) > 1:
        _cron_decide(layout, args[1], approve=True)
    elif sub == "reject" and len(args) > 1:
        _cron_decide(layout, args[1], approve=False)
    elif sub == "remove" and len(args) > 1:
        _cron_remove(layout, args[1], remove_all="--all" in args)
    else:
        print("  usage: /cron list | add | approve <id> | reject <id> | remove <id> [--all]")


def _cron_list(layout: Layout) -> None:
    agenda = load_agenda(layout)
    tasks = agenda.get("tasks", [])
    if not tasks:
        print("  no scheduled tasks")
        return
    for t in tasks:
        status = t.get("status", "?")
        tid = t.get("id", "?")
        desc = t.get("description", "")
        executor = t.get("executor", "?")
        schedule = t.get("schedule", "?")
        last_run = t.get("last_run") or "never"
        print(f"  [{status}] {tid}  {executor}  {schedule}  last:{last_run}")
        print(f"         {desc}")


def _build_wake_up_message(task: str, executor: str, tools: str = "") -> str:
    """Generate wake_up_message from task fields."""
    if executor == "worker":
        return (
            f"[Task] {task}\n"
            "[Persona] FCP autonomous worker — concise, factual, no fluff.\n"
            "[Constraints] Read-only. Do not write files, send messages, or modify any state. "
            "Reason only from provided context. Return only the result."
        )
    msg = f"[Task] {task}"
    if tools:
        msg += f"\n[Tools] {tools}"
    return msg


def _cron_add_interactive(layout: Layout) -> None:
    """Prompt Operator interactively for all cron fields, then save as approved."""
    import datetime as _dt
    fields = [
        ("description", "Description (human-readable summary): "),
        ("executor",    "Executor [worker/cpe]: "),
        ("tools",       "Tools/skills (leave blank if none): "),
        ("task",        "Task (clear, verifiable instruction): "),
        ("schedule",    "Schedule (cron expression, e.g. 0 9 * * 1-5): "),
    ]
    values: dict[str, str] = {}
    print()
    for key, prompt in fields:
        val = ui.ask(prompt.rstrip(": "))
        if val == "" and key in ("description", "task", "schedule"):
            ui.print_info("aborted.")
            return
        values[key] = val

    executor = values.get("executor", "").lower()
    if executor not in ("worker", "cpe"):
        print("  invalid executor — must be 'worker' or 'cpe'. aborted.")
        return
    required = ("description", "task", "schedule")
    if not all(values.get(f) for f in required):
        print("  missing required fields. aborted.")
        return

    wake_up_message = _build_wake_up_message(values["task"], executor, values.get("tools", ""))

    print(f"\n  description   : {values['description']}")
    print(f"  executor      : {executor}")
    print(f"  tools         : {values.get('tools') or '(none)'}")
    print(f"  task          : {values['task']}")
    print(f"  schedule      : {values['schedule']}")
    print(f"  wake_up_msg   : {wake_up_message}")
    print()
    if not ui.confirm("Save and approve?", default=False):
        ui.print_info("aborted.")
        return

    import uuid as _uuid
    now = _dt.datetime.utcnow().isoformat() + "Z"
    task_entry = {
        "id": f"cron_{_uuid.uuid4().hex[:12]}",
        "status": "approved",
        "executor": executor,
        "description": values["description"],
        "tools": values.get("tools", ""),
        "task": values["task"],
        "schedule": values["schedule"],
        "wake_up_message": wake_up_message,
        "proposed_at": now,
        "approved_at": now,
        "last_run": None,
    }
    agenda = load_agenda(layout)
    agenda.setdefault("tasks", []).append(task_entry)
    layout.agenda.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(layout.agenda, agenda)
    _cron_register_host(task_entry, layout)
    print(f"  created and approved: {task_entry['id']}")


def _cron_decide(layout: Layout, cron_id: str, approve: bool) -> None:
    agenda = load_agenda(layout)
    tasks = agenda.get("tasks", [])
    task = next((t for t in tasks if t.get("id") == cron_id), None)
    if task is None:
        print(f"  task not found: {cron_id}")
        return
    if task.get("status") != "pending":
        print(f"  task is not pending: {cron_id} (status: {task.get('status')})")
        return
    if approve:
        import datetime as _dt
        task["status"] = "approved"
        task["approved_at"] = _dt.datetime.utcnow().isoformat() + "Z"
        atomic_write(layout.agenda, agenda)
        _cron_register_host(task, layout)
        print(f"  approved: {cron_id}")
    else:
        agenda["tasks"] = [t for t in tasks if t.get("id") != cron_id]
        atomic_write(layout.agenda, agenda)
        print(f"  rejected and removed: {cron_id}")


def _cron_remove(layout: Layout, cron_id: str, remove_all: bool = False) -> None:
    agenda = load_agenda(layout)
    tasks = agenda.get("tasks", [])
    if remove_all:
        removed = len(tasks)
        for t in tasks:
            _cron_unregister_host(t.get("id", ""), layout)
        agenda["tasks"] = []
        atomic_write(layout.agenda, agenda)
        print(f"  removed all {removed} task(s)")
        return
    task = next((t for t in tasks if t.get("id") == cron_id), None)
    if task is None:
        print(f"  task not found: {cron_id}")
        return
    _cron_unregister_host(cron_id, layout)
    agenda["tasks"] = [t for t in tasks if t.get("id") != cron_id]
    atomic_write(layout.agenda, agenda)
    print(f"  removed: {cron_id}")


def _cron_register_host(task: dict, layout: Layout) -> None:
    """Register cron entry in the host crontab."""
    import subprocess
    cron_id = task.get("id", "")
    schedule = task.get("schedule", "")
    if not schedule or not cron_id:
        return
    fcp_bin = layout.root / "fcp"
    cron_line = f"{schedule} {fcp_bin} --auto {cron_id}  # fcp:{cron_id}"
    # read current crontab, append, write back
    r = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    existing = r.stdout if r.returncode == 0 else ""
    # remove any stale entry for this id first
    lines = [l for l in existing.splitlines() if f"# fcp:{cron_id}" not in l]
    lines.append(cron_line)
    new_crontab = "\n".join(lines) + "\n"
    subprocess.run(["crontab", "-"], input=new_crontab, text=True)
    print(f"  crontab registered: {schedule}")


def _cron_unregister_host(cron_id: str, layout: Layout) -> None:
    """Remove cron entry from host crontab."""
    import subprocess
    if not cron_id:
        return
    r = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    if r.returncode != 0:
        return
    lines = [l for l in r.stdout.splitlines() if f"# fcp:{cron_id}" not in l]
    new_crontab = "\n".join(lines) + "\n"
    subprocess.run(["crontab", "-"], input=new_crontab, text=True)


# --- CMI ---

def _cmd_cmi(layout: Layout, args: list[str]) -> None:
    if not args:
        _cmi_usage()
        return
    sub = args[0].lower()
    if sub == "status":
        _cmi_status(layout)
    elif sub == "start":
        _cmi_start(layout)
    elif sub == "stop":
        _cmi_stop(layout)
    elif sub == "token":
        _cmi_export(layout)
    elif sub == "invite":
        _cmi_contacts_add(layout)
    elif sub == "contacts":
        _cmi_contacts(layout, args[1:])
    elif sub in ("chan", "channel"):
        _cmi_channel(layout, args[1:])
    elif sub == "bb" and len(args) > 1:
        _cmi_bb(layout, args[1])
    else:
        _cmi_usage()


def _cmi_usage() -> None:
    print("  usage: /cmi start | stop | status | token | invite | contacts [list|add|remove] | chan [list|open|close] | bb <id>")


def _cmi_start(layout: Layout) -> None:
    """Activate CMI: generate credential if needed, configure endpoint, trigger endure."""
    import json as _json
    from .cmi.identity import generate_cmi_credential, load_cmi_credential
    from .store import read_json, atomic_write

    cred = load_cmi_credential(layout)
    if cred is None:
        try:
            cred = generate_cmi_credential(layout)
            print(f"  credential generated — node: {cred['node_identity']}")
        except RuntimeError as exc:
            print(f"  error: {exc}")
            return

    baseline: dict = {}
    if layout.baseline.exists():
        try:
            baseline = read_json(layout.baseline)
        except Exception:
            pass

    cmi_cfg = baseline.get("cmi", {})
    existing_host = cmi_cfg.get("host", "")
    if existing_host:
        host = ui.ask("CMI endpoint", default=existing_host)
    else:
        host = ui.ask("CMI endpoint", default="localhost:7000")

    # build proposal content — sleep cycle applies and covers in Integrity Document
    credential_content = _json.dumps({
        "node_identity": cred["node_identity"],
        "privkey": cred["privkey"],
        "pubkey": cred["pubkey"],
        "created_at": cred["created_at"],
    }, indent=2)
    content = _json.dumps({
        "changes": [
            {
                "op": "json_merge",
                "target": "state/baseline.json",
                "patch": {"cmi": {"enabled": True, "host": host}},
            },
            {
                "op": "file_write",
                "target": "state/cmi/credential.json",
                "content": credential_content,
            },
        ]
    })
    auth_digest = _sha256_str(content)
    _write_evolution_auth(layout, content, auth_digest)
    set_endure_approved(True)
    print("  CMI activation queued — session will close for Sleep Cycle and reboot")


def _cmi_stop(layout: Layout) -> None:
    """Deactivate CMI: set enabled=false in baseline, trigger endure."""
    import json as _json
    from .store import read_json

    baseline: dict = {}
    if layout.baseline.exists():
        try:
            baseline = read_json(layout.baseline)
        except Exception:
            pass
    if not baseline.get("cmi", {}).get("enabled", False):
        print("  CMI is already disabled")
        return

    content = _json.dumps({
        "changes": [
            {
                "op": "json_merge",
                "target": "state/baseline.json",
                "patch": {"cmi": {"enabled": False}},
            },
        ]
    })
    auth_digest = _sha256_str(content)
    _write_evolution_auth(layout, content, auth_digest)
    set_endure_approved(True)
    print("  CMI deactivation queued — session will close for Sleep Cycle and reboot")


def _cmi_status(layout: Layout) -> None:
    """Show CMI node status and active channels."""
    from .cmi.identity import load_cmi_credential
    cred = load_cmi_credential(layout)
    if cred is None:
        print("  CMI not activated — no credential found")
        print("  (run /cmi start to activate)")
        return
    print(f"  node identity : {cred['node_identity']}")
    baseline = {}
    if layout.baseline.exists():
        try:
            baseline = read_json(layout.baseline)
        except Exception:
            pass
    cmi_cfg = baseline.get("cmi", {})
    endpoint = cmi_cfg.get("host", "(not configured)")
    enabled = cmi_cfg.get("enabled", False)
    print(f"  endpoint      : {endpoint}")
    print(f"  enabled       : {enabled}")
    # active channels from state/cmi/channels/
    channels: list[str] = []
    if layout.cmi_channels_dir.exists():
        channels = [d.name for d in sorted(layout.cmi_channels_dir.iterdir()) if d.is_dir()]
    if channels:
        print(f"  channels      : {len(channels)} active")
        for c in channels:
            participants_path = layout.cmi_participants(c)
            role = "?"
            status = "?"
            if participants_path.exists():
                try:
                    p = read_json(participants_path)
                    role = p.get("local_role", "?")
                    status = p.get("status", "?")
                except Exception:
                    pass
            print(f"    {c}  role:{role}  status:{status}")
    else:
        print("  channels      : none")


def _cmi_peers(layout: Layout) -> None:
    """List trusted peers from baseline.cmi.trusted_peers."""
    baseline = {}
    if layout.baseline.exists():
        try:
            baseline = read_json(layout.baseline)
        except Exception:
            pass
    peers = baseline.get("cmi", {}).get("trusted_peers", [])
    if not peers:
        print("  no trusted peers configured")
        print("  (add peers via evolution_proposal with op cmi_peer_add)")
        return
    for p in peers:
        alias = p.get("alias", "?")
        ni = p.get("node_identity", "?")
        label = p.get("trust_label", "?")
        endpoint = p.get("endpoint", "?")
        print(f"  {alias}  [{label}]  {ni[:20]}...  {endpoint}")


def _cmi_export(layout: Layout) -> None:
    """Export this entity's invite token for sharing with a peer Operator."""
    from .cmi.identity import export_invite_token
    try:
        token = export_invite_token(layout)
    except RuntimeError as exc:
        print(f"  error: {exc}")
        return
    print("  invite token (share this with the peer Operator):")
    print()
    print(f"  {token}")
    print()
    print("  peer adds it with: /cmi invite")


def _cmi_contacts(layout: Layout, args: list[str]) -> None:
    sub = args[0].lower() if args else "list"
    if sub == "list":
        _cmi_contacts_list(layout)
    elif sub == "add":
        _cmi_contacts_add(layout)
    elif sub == "remove" and len(args) > 1:
        _cmi_contacts_remove(layout, args[1])
    else:
        print("  usage: /cmi contacts [list|add|remove <node_id>]")


def _cmi_contacts_list(layout: Layout) -> None:
    """List trusted contacts from baseline.cmi.contacts."""
    baseline = {}
    if layout.baseline.exists():
        try:
            baseline = read_json(layout.baseline)
        except Exception:
            pass
    contacts = baseline.get("cmi", {}).get("contacts", [])
    # also support legacy trusted_peers key
    if not contacts:
        contacts = baseline.get("cmi", {}).get("trusted_peers", [])
    if not contacts:
        print("  no contacts — use /cmi contacts add to add one")
        return
    for c in contacts:
        label = c.get("label", c.get("alias", "?"))
        node_id = c.get("node_id", c.get("node_identity", "?"))
        endpoint = c.get("endpoint", "?")
        added = c.get("added_at", "")
        print(f"  {label}  {node_id[:20]}...  {endpoint}  added:{added}")


def _cmi_contacts_add(layout: Layout) -> None:
    """Interactively add a contact from a peer's invite token."""
    from .cmi.identity import import_invite_token

    ui.print_info("paste the invite token from the peer Operator:")
    try:
        token = ui.ask("token")
    except KeyboardInterrupt:
        ui.print_info("cancelled")
        return

    if not token:
        ui.print_info("cancelled — no token provided")
        return

    try:
        contact = import_invite_token(token)
    except ValueError as exc:
        print(f"  error: {exc}")
        return

    print()
    print(f"  label    : {contact['label']}")
    print(f"  node_id  : {contact['node_id']}")
    print(f"  endpoint : {contact['endpoint']}")
    print(f"  pubkey   : {contact['pubkey'][:16]}...")
    print()

    if not ui.confirm("add this contact?", default=False):
        ui.print_info("cancelled")
        return

    # Write contact to baseline.cmi.contacts
    baseline = {}
    if layout.baseline.exists():
        try:
            baseline = read_json(layout.baseline)
        except Exception:
            pass

    # Block self-add
    from .cmi.identity import load_cmi_credential
    own_cred = load_cmi_credential(layout)
    if own_cred and contact["node_id"] == own_cred.get("node_identity"):
        print("  error: cannot add own entity as contact")
        return

    cmi_cfg = baseline.setdefault("cmi", {})
    contacts = cmi_cfg.setdefault("contacts", [])

    # Check for duplicate node_id
    if any(c.get("node_id") == contact["node_id"] for c in contacts):
        print(f"  contact already exists: {contact['label']}")
        return

    contacts.append(contact)
    atomic_write(layout.baseline, baseline)
    print(f"  contact added: {contact['label']}")


def _cmi_contacts_remove(layout: Layout, node_id: str) -> None:
    """Remove a contact by node_id (or label prefix) from baseline.cmi.contacts."""
    baseline: dict = {}
    if layout.baseline.exists():
        try:
            baseline = read_json(layout.baseline)
        except Exception:
            pass
    cmi_cfg = baseline.get("cmi", {})
    contacts = cmi_cfg.get("contacts", [])
    # match by node_id or label
    match = [c for c in contacts if c.get("node_id") == node_id or c.get("label") == node_id]
    if not match:
        print(f"  contact not found: {node_id}")
        return
    entry = match[0]
    cmi_cfg["contacts"] = [c for c in contacts if c.get("node_id") != entry["node_id"]]
    baseline["cmi"] = cmi_cfg
    atomic_write(layout.baseline, baseline)
    print(f"  contact removed: {entry.get('label', node_id)}")


def _cmi_channel(layout: Layout, args: list[str]) -> None:
    if not args:
        print("  usage: /cmi chan list | open [<id>] | close <id>")
        return
    sub = args[0].lower()
    if sub == "list":
        _cmi_channel_list(layout)
    elif sub == "open":
        chan_id = args[1] if len(args) > 1 else None
        _cmi_channel_open(layout, chan_id)
    elif sub == "close" and len(args) > 1:
        _cmi_channel_close(layout, args[1])
    else:
        print("  usage: /cmi chan list | open [<id>] | close <id>")


def _cmi_channel_list(layout: Layout) -> None:
    """List channels declared in baseline.cmi.channels."""
    baseline = {}
    if layout.baseline.exists():
        try:
            baseline = read_json(layout.baseline)
        except Exception:
            pass
    channels = baseline.get("cmi", {}).get("channels", [])
    if not channels:
        print("  no channels configured — use /cmi chan open to create one")
        return
    for ch in channels:
        cid = ch.get("id", "?")
        task = ch.get("task", "?")
        role = ch.get("role", "?")
        status = ch.get("status", "?")
        n_participants = len(ch.get("participants", []))
        print(f"  {cid}  [{status}]  role:{role}  peers:{n_participants}")
        print(f"         {task[:72]}")


def _cmi_channel_create_interactive(layout: Layout, baseline: dict, cred: dict) -> str | None:
    """Interactively create a new channel entry in baseline and return its chan_id."""
    import time as _time

    contacts = baseline.get("cmi", {}).get("contacts", [])
    if not contacts:
        print("  no contacts available — add one first with /cmi contacts add")
        return None

    print("  available contacts:")
    for i, c in enumerate(contacts):
        print(f"    [{i}] {c.get('label', '?')}  {c.get('node_id', '?')[:20]}...  {c.get('endpoint', '?')}")
    print()

    try:
        sel = ui.ask("select contact index")
        idx = int(sel)
        if idx < 0 or idx >= len(contacts):
            raise ValueError()
    except (ValueError, KeyboardInterrupt, EOFError):
        ui.print_info("cancelled")
        return None

    contact = contacts[idx]

    task = ui.ask("task description")
    if not task:
        ui.print_info("cancelled — task is required")
        return None

    chan_id = f"chan_{int(_time.time())}"
    channel = {
        "id": chan_id,
        "task": task,
        "role": "host",
        "status": "created",
        "participants": [contact["node_id"]],
    }

    cmi_cfg = baseline.setdefault("cmi", {})
    channels = cmi_cfg.setdefault("channels", [])
    channels.append(channel)
    atomic_write(layout.baseline, baseline)

    print(f"  channel created: {chan_id}  task: {task[:60]}")
    return chan_id


def _cmi_channel_open(layout: Layout, chan_id: str | None) -> None:
    """Launch CMI subprocess for a channel. Interactively creates one if chan_id is None."""
    import subprocess
    from .cmi.identity import load_cmi_credential

    # Validate CMI is activated
    cred = load_cmi_credential(layout)
    if cred is None:
        print("  CMI not activated — no credential found")
        return

    baseline = {}
    if layout.baseline.exists():
        try:
            baseline = read_json(layout.baseline)
        except Exception:
            pass

    # Interactive channel creation if no chan_id provided
    if chan_id is None:
        chan_id = _cmi_channel_create_interactive(layout, baseline, cred)
        if chan_id is None:
            return
        # Reload baseline after creation
        try:
            baseline = read_json(layout.baseline)
        except Exception:
            pass

    channels = baseline.get("cmi", {}).get("channels", [])
    ch = next((c for c in channels if c.get("id") == chan_id), None)
    if ch is None:
        print(f"  channel not found in baseline: {chan_id}")
        return
    if ch.get("status") not in ("created", "active"):
        print(f"  channel status is '{ch.get('status')}' — cannot open")
        return

    role = ch.get("role", "peer")

    # Check session token — CMI requires active session
    if not layout.session_token.exists():
        print("  no active session — CMI requires a session token")
        return

    # Check for existing channel process (participants.json status=active)
    p_path = layout.cmi_participants(chan_id)
    if p_path.exists():
        try:
            p = read_json(p_path)
            if p.get("status") == "active":
                print(f"  channel already active: {chan_id}")
                return
        except Exception:
            pass

    # Check if port is already in use before launching
    import socket as _socket
    from urllib.parse import urlparse as _urlparse
    _ep = baseline.get("cmi", {}).get("endpoint", "http://localhost:7700")
    _parsed = _urlparse(_ep)
    _host = _parsed.hostname or "localhost"
    _port = _parsed.port or 7700
    with _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM) as _s:
        if _s.connect_ex((_host, _port)) == 0:
            print(f"  port {_port} is already in use — cannot open channel process")
            print(f"  (another channel may be active, or a previous process is still running)")
            return

    # Launch channel_process as a background subprocess
    import sys
    cmd = [
        sys.executable, "-m", "fcp_base.cmi.channel_process",
        str(layout.root), chan_id, role,
    ]
    proc = subprocess.Popen(
        cmd,
        cwd=str(layout.root),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    print(f"  channel process launched: {chan_id}  role:{role}  pid:{proc.pid}")


def _cmi_channel_close(layout: Layout, chan_id: str) -> None:
    """Signal close to an active CMI channel via HTTP POST."""
    import urllib.request, urllib.error

    # Read close_token from Entity Store — only the local Operator can do this
    close_token = ""
    token_path = layout.cmi_close_token(chan_id)
    if token_path.exists():
        try:
            close_token = read_json(token_path).get("token", "")
        except Exception:
            pass
    if not close_token:
        print(f"  close_token not found for channel {chan_id} — is the channel process running?")
        return

    baseline = {}
    if layout.baseline.exists():
        try:
            baseline = read_json(layout.baseline)
        except Exception:
            pass
    cmi_cfg = baseline.get("cmi", {})
    endpoint = cmi_cfg.get("endpoint", "http://localhost:7700")

    url = f"{endpoint}/channel/{chan_id}/close"
    body = json.dumps({"close_token": close_token}).encode()
    try:
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5):
            pass
        print(f"  close signal sent: {chan_id}")
    except urllib.error.URLError as exc:
        print(f"  could not reach channel process: {exc.reason}")
        print(f"  (process may have already exited)")


def _cmi_bb(layout: Layout, chan_id: str) -> None:
    """Display Blackboard contents for a channel."""
    from .store import read_jsonl
    bb_path = layout.cmi_blackboard(chan_id)
    if not bb_path.exists():
        print(f"  no blackboard found for channel: {chan_id}")
        return
    entries = read_jsonl(bb_path)
    if not entries:
        print(f"  blackboard empty: {chan_id}")
        return
    print(f"  blackboard: {chan_id}  ({len(entries)} entries)")
    for e in entries:
        seq = e.get("seq", "?")
        contributor = str(e.get("from", "?"))[:16]
        content = str(e.get("content", ""))[:80]
        print(f"  [{seq}] {contributor}...  {content}")


# --- Compact ---

def _cmd_compact() -> None:
    global _compact_pending
    _compact_pending = True
    print("  compact: session compaction requested — awaiting closure payload from CPE")


# --- Debug ---

def _cmd_verbose(layout: Layout, args: list[str]) -> None:
    global _verbose, _debugger
    if args and args[0] == "--off":
        _verbose = False
    else:
        _verbose = True
    if _verbose and _debugger is not None:
        _debugger = None
        print("  debugger: off (switched to verbose)")
    print(f"  verbose: {'on' if _verbose else 'off'}")


def _cmd_debugger(layout: Layout, args: list[str]) -> None:
    global _verbose, _debugger
    flag = next((a for a in args if a.startswith("--")), None)
    if flag == "--off":
        _debugger = None
        print("  debugger: off")
        return
    mode = flag.lstrip("-") if flag else "all"
    if mode not in ("all", "chat", "boot"):
        print("  usage: /debugger [--all | --chat | --boot | --off]")
        return
    _debugger = mode
    if _verbose:
        _verbose = False
        print("  verbose: off (switched to debugger)")
    print(f"  debugger: on --{mode}")


def _cmd_help() -> None:
    print("""
  Platform commands:

  Session:
    /status                   — entity status overview
    /model [list]             — interactive model picker (active model highlighted)
    /exit | /bye | /close     — close session
    /new | /clear | /reset    — forced close + clean session restart
    /compact                  — compress session context without closing

  Memory:
    /memory [query]           — list memory store contents (episodic + semantic)
    /inbox list               — list system notifications
    /inbox view <id>          — view notification by index
    /inbox dismiss <id>       — remove notification by index
    /inbox clear              — remove all notifications

  Workspace:
    /work status              — show active workspace focus
    /work set <subdir>        — set workspace focus
    /work clone <repo>        — clone repo and set as workspace focus
    /work clear               — unset workspace focus

  Skills:
    /skill list               — list installed skills
    /skill add                — create new skill
    /skill run <name> [k=v]   — run a skill directly with optional params
    /skill audit <name>       — audit a skill
    /allowlist list           — list shell_run allowlists
    /allowlist allow <cmd> [label]
                              — add composite command to allowlist
    /allowlist remove <idx|label>
                              — remove composite command from allowlist

  Evolution:
    /endure list              — list pending Evolution Proposals
    /endure approve <id>      — approve proposal by index
    /endure reject <id>       — reject proposal by index
    /endure chain             — display integrity chain

  Agenda:
    /cron list                — list scheduled tasks
    /cron add                 — create task interactively (Operator-initiated)
    /cron approve <id>        — approve pending task proposal; registers cron on host
    /cron reject <id>         — reject pending task proposal
    /cron remove <id> [--all] — remove task and unregister from host crontab

  CMI (Cognitive Mesh Interface):
    /cmi start                — activate CMI (generates credential, configures endpoint, triggers endure)
    /cmi stop                 — deactivate CMI (preserves credential and contacts, triggers endure)
    /cmi status               — node identity, endpoint, active channels
    /cmi token                — generate invite token to share with a peer Operator
    /cmi invite               — add a contact from a peer's invite token (interactive)
    /cmi contacts list        — list trusted contacts
    /cmi contacts remove <id> — remove a contact by node_id or label
    /cmi chan list             — list declared channels from baseline
    /cmi chan open             — create and launch a new channel (interactive)
    /cmi chan open <id>        — launch CMI process for an existing channel
    /cmi chan close <id>       — signal close to an active channel
    /cmi bb <id>               — display Blackboard contents for a channel

  Debug:
    /doctor [--fix]           — check and optionally repair integrity
    /verbose [--off]          — enable component message summary (--off to disable)
    /debugger [--all|--chat|--boot|--off]
                              — inspect CPE context (disables verbose)
                                --all:  full context (default)
                                --chat: session history only
                                --boot: system + instruction block only
                                --off:  disable debugger

    /help                     — this message
""")


# ---------------------------------------------------------------------------
# Skill alias dispatch  §12.3.2
# ---------------------------------------------------------------------------

def resolve_alias(layout: Layout, line: str) -> str | None:
    """Return skill name if line matches an alias in skills/index.json, else None."""
    if not layout.skills_index.exists():
        return None
    try:
        idx = read_json(layout.skills_index)
        aliases: dict[str, Any] = idx.get("aliases", {})
        cmd = line.strip().split()[0].lower() if line.strip() else ""
        entry = aliases.get(cmd)
        if entry is None:
            return None
        if isinstance(entry, dict):
            return str(entry.get("skill", ""))
        return str(entry)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


# Removed: _write_evolution_stimuli (now in stimuli.py)
# Removed: _write_evolution_auth (now in sil.py)


def _write_evolution_rejected(layout: Layout, content: str) -> None:
    ts = int(time.time() * 1000)
    envelope = acp_encode(
        env_type="MSG",
        source="operator",
        data={"type": "EVOLUTION_REJECTED", "ts": ts},
    )
    append_jsonl(layout.integrity_log, envelope)
