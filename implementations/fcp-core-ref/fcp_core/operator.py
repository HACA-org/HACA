"""
Operator Interface — FCP-Core §12.

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
from .sil import sha256_str as _sha256_str
from .store import Layout, append_jsonl, atomic_write, read_json


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
        try:
            answer = input("Approve? [y/N] ").strip().lower()
        except EOFError:
            answer = "n"
        if answer == "y":
            auth_digest = _sha256_str(content)
            authorized.append({
                "seq": inner.get("ts", int(time.time() * 1000)),
                "content": content,
                "auth_digest": auth_digest,
                "slugs": inner.get("slugs", []),
            })
            _write_evolution_auth(layout, content, auth_digest)
        else:
            _write_evolution_rejected(layout, content)
        pfile = p["file"]
        if isinstance(pfile, Path):
            pfile.unlink(missing_ok=True)

    return authorized


# ---------------------------------------------------------------------------
# Platform commands  §12.3.1
# ---------------------------------------------------------------------------

def handle_platform_command(layout: Layout, line: str, adapter_ref: Any = None) -> bool:
    """Handle a /command line. Returns True if handled, False if unknown."""
    parts = line.strip().split()
    if not parts:
        return False
    cmd = parts[0].lower()
    args = list(itertools.islice(parts, 1, len(parts)))

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
    if cmd == "/skill":
        _cmd_skill(layout, args)
        return True

    # --- Model & endure ---
    if cmd == "/model":
        _cmd_model(layout, args, adapter_ref)
        return True
    if cmd == "/endure":
        _cmd_endure(layout, args)
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


def _cmd_doctor(layout: Layout, args: list[str]) -> None:
    from .compliance import run_all, print_report
    fix = "--fix" in args
    if fix:
        for d in layout.volatile_dirs():
            if not d.exists():
                d.mkdir(parents=True, exist_ok=True)
                print(f"  created: {d.relative_to(layout.root)}")
        fix_integrity_hashes(layout)
    findings = run_all(layout)
    print_report(findings)
    failed = [f for f in findings if not f.passed]
    if failed:
        print(f"\n  {len(failed)} issue(s) found. Run /doctor --fix to repair volatile dirs.")


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
    sub = args[0].lower() if args else "list"

    if sub == "list":
        _inbox_list(layout)
    elif sub == "view" and len(args) > 1:
        _inbox_view(layout, args[1])
    elif sub == "dismiss" and len(args) > 1:
        _inbox_dismiss(layout, args[1])
    elif sub == "clear":
        _inbox_clear(layout)
    else:
        print("  usage: /inbox [list] | view <n> | dismiss <n> | clear")


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
        print("  usage: /work set <subdir> | clone <repo>")
        return
    sub = args[0].lower()
    if sub == "set" and len(args) > 1:
        subdir = args[1]
        target = (layout.workspace_dir / subdir).resolve()
        try:
            target.relative_to(layout.workspace_dir)
        except ValueError:
            print(f"  path outside workspace: {subdir}")
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
                try:
                    answer = input(f"  workspace focus already set to {current!r}. Overwrite? [y/N] ").strip().lower()
                except EOFError:
                    answer = "n"
                if answer != "y":
                    print("  aborted.")
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

def _cmd_skill(layout: Layout, args: list[str]) -> None:
    if not args:
        print("  usage: /skill list | audit <name>")
        return
    sub = args[0].lower()
    if sub == "list":
        if layout.skills_index.exists():
            idx = read_json(layout.skills_index)
            for s in idx.get("skills", []):
                print(f"  {s['name']} [{s.get('class', '?')}]")
        else:
            print("  skills/index.json not found")
    elif sub == "audit" and len(args) > 1:
        print(f"  audit {args[1]}: use /skill audit via EXEC dispatch during session")
    else:
        print("  usage: /skill list | audit <name>")


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
    try:
        new_adapter = make_adapter(backend=backend, model=new_model, api_key="")
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
    import sys, tty, termios
    from .cpe.base import KNOWN_MODELS, BACKENDS

    # Build flat list of "backend:model" labels
    labels: list[str] = []
    pairs: list[tuple[str, str]] = []

    def _ollama_models() -> list[str]:
        try:
            import urllib.request, json as _j
            with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2) as r:
                return [m["name"] for m in _j.loads(r.read().decode()).get("models", [])]
        except Exception:
            return []

    for backend in BACKENDS:
        models = _ollama_models() if backend == "ollama" else KNOWN_MODELS.get(backend, [])
        for m in models:
            active = backend == current_backend and m == current_model
            label = f"\x1b[1;96m{backend}:{m} ✓\x1b[0m" if active else f"{backend}:{m}"
            labels.append(label)
            pairs.append((backend, m))

    if not labels:
        print("  no models available")
        return None

    sel_idx = next(
        (i for i, (b, m) in enumerate(pairs) if b == current_backend and m == current_model),
        0,
    )

    first_render = True

    def _render(sidx: int) -> None:
        nonlocal first_render
        if not first_render:
            sys.stdout.write(f"\033[{len(labels)}A")
        first_render = False
        for i, label in enumerate(labels):
            prefix = " > " if i == sidx else "   "
            sys.stdout.write(f"\r{prefix}{label}\033[K\n")
        sys.stdout.flush()

    print("Select model (↑↓ to move, Enter to confirm, Ctrl+C to cancel):")
    _render(sel_idx)

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        while True:
            ch = sys.stdin.read(1)
            if ch in ("\r", "\n"):
                break
            if ch == "\x03":
                print()
                return None
            if ch == "\x1b":
                ch2 = sys.stdin.read(1)
                ch3 = sys.stdin.read(1)
                if ch2 == "[":
                    if ch3 == "A" and sel_idx > 0:
                        sel_idx -= 1
                    elif ch3 == "B" and sel_idx < len(labels) - 1:
                        sel_idx += 1
            _render(sel_idx)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)

    print()
    return pairs[sel_idx]


def _model_list_print(backend: str) -> None:
    from .cpe.base import KNOWN_MODELS
    print(f"  backend: {backend}")
    for b, models in KNOWN_MODELS.items():
        marker = " (current)" if b == backend else ""
        print(f"  ── {b}{marker}")
        for m in models:
            print(f"       {m}")


def _cmd_endure(layout: Layout, args: list[str]) -> None:
    if not args:
        print("  usage: /endure list | approve <n> | reject <n> | sync [--remote]")
        return
    sub = args[0].lower()
    if sub == "list":
        _endure_list(layout)
    elif sub == "approve" and len(args) > 1:
        _endure_decide(layout, args[1], approve=True)
    elif sub == "reject" and len(args) > 1:
        _endure_decide(layout, args[1], approve=False)
    elif sub == "sync":
        _endure_sync(layout, "--remote" in args)
    else:
        print(f"  unknown endure subcommand: {sub}")


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
        print(f"  approved: [{idx}] — session will close for Sleep Cycle and reboot")
        set_endure_approved(True)
        from .hooks import run_hook
        run_hook(layout, "on_evolution_authorized", {"content": content[:256], "auth_digest": auth_digest})
    else:
        _write_evolution_rejected(layout, content)
        print(f"  rejected: [{idx}]")
        from .hooks import run_hook
        run_hook(layout, "on_evolution_rejected", {"content": content[:256]})
    pfile = p["file"]
    if isinstance(pfile, Path):
        pfile.unlink(missing_ok=True)


def _endure_sync(layout: Layout, remote: bool) -> None:
    import subprocess
    r = subprocess.run(["git", "add", "-A"], capture_output=True, text=True, cwd=str(layout.root))
    if r.returncode != 0:
        print(f"  git add failed: {r.stderr.strip()}")
        return
    ts = int(time.time())
    r2 = subprocess.run(
        ["git", "commit", "-m", f"endure sync {ts}"],
        capture_output=True, text=True, cwd=str(layout.root),
    )
    if r2.returncode != 0:
        print(f"  git commit: {r2.stderr.strip() or 'nothing to commit'}")
    else:
        print(f"  committed: {r2.stdout.strip()}")
    if remote:
        r3 = subprocess.run(["git", "push", "origin"], capture_output=True, text=True, cwd=str(layout.root))
        print(f"  push: {'ok' if r3.returncode == 0 else r3.stderr.strip()}")


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

  Entity & session:
    /status                      — entity status overview
    /doctor [--fix]              — check and optionally repair integrity
    /exit | /bye | /close        — close session
    /new | /clear | /reset       — forced close + clean session restart
    /compact                     — compress session context without closing

  Memory & inbox:
    /memory [query]              — list memory store contents (episodic + semantic)
    /inbox [list]                — list system notifications
    /inbox view <n>              — view notification by index
    /inbox dismiss <n>           — remove notification by index
    /inbox clear                 — remove all notifications

  Workspace:
    /work status                 — show active workspace focus
    /work set <subdir>           — set workspace focus
    /work clone <repo>           — clone repo and set as workspace focus
    /work clear                  — unset workspace focus

  Skills & execution:
    /skill list                  — list installed skills
    /skill audit <name>          — audit a skill

  Model & endure:
    /model                       — interactive model picker (active model highlighted)
    /model list                  — alias for /model
    /endure list                 — list pending Evolution Proposals
    /endure approve <n>          — approve proposal by index
    /endure reject <n>           — reject proposal by index
    /endure sync [--remote]      — commit entity root to version control

  Debug:
    /verbose [--off]             — enable component message summary (--off to disable)
    /debugger [--all|--chat|--boot|--off]
                                 — inspect CPE context (disables verbose)
                                   --all:  full context (default)
                                   --chat: session history only
                                   --boot: system + instruction block only
                                   --off:  disable debugger

    /help                        — this message
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


def _write_evolution_auth(layout: Layout, content: str, auth_digest: str) -> None:
    ts = int(time.time() * 1000)
    try:
        parsed_content = json.loads(content)
    except Exception:
        parsed_content = content
    envelope = acp_encode(
        env_type="MSG",
        source="operator",
        data={"type": "EVOLUTION_AUTH", "auth_digest": auth_digest, "content": parsed_content, "ts": ts},
    )
    append_jsonl(layout.integrity_log, envelope)


def _write_evolution_rejected(layout: Layout, content: str) -> None:
    ts = int(time.time() * 1000)
    envelope = acp_encode(
        env_type="MSG",
        source="operator",
        data={"type": "EVOLUTION_REJECTED", "ts": ts},
    )
    append_jsonl(layout.integrity_log, envelope)
