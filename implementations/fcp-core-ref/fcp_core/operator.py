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
from .store import Layout, append_jsonl, atomic_write, read_json


# ---------------------------------------------------------------------------
# Debug state — session-scoped, not persisted
# ---------------------------------------------------------------------------

_verbose: bool = False
_debugger: str | None = None  # None | "all" | "chat" | "boot"


def is_verbose() -> bool:
    return _verbose


def set_verbose(value: bool) -> None:
    global _verbose
    _verbose = value


def get_debugger() -> str | None:
    return _debugger


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
            print(f"  directory not found: {subdir}")
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
    else:
        print("  usage: /work set <subdir> | clone <repo>")


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

    if not args:
        print(f"  current model  : {cpe_cfg.get('model', '(not set)')}")
        print(f"  backend        : {cpe_cfg.get('backend', '(not set)')}")
        return

    sub = args[0].lower()

    if sub == "list":
        _model_list(cpe_cfg.get("backend", ""))
        return

    # /model <name> — swap adapter mid-session
    new_model = args[0]
    if adapter_ref is None:
        print("  /model <name> is only available during an active session")
        return
    from .cpe.base import make_adapter
    try:
        new_adapter = make_adapter(
            backend=cpe_cfg.get("backend", "ollama"),
            model=new_model,
            api_key="",
        )
    except Exception as exc:
        print(f"  failed to create adapter: {exc}")
        return
    adapter_ref.current = new_adapter
    # persist to baseline
    cpe_cfg["model"] = new_model
    baseline["cpe"] = cpe_cfg
    from .store import atomic_write
    atomic_write(layout.baseline, baseline)
    print(f"  model switched : {new_model}")


def _model_list(backend: str) -> None:
    known: dict[str, list[str]] = {
        "anthropic": ["claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"],
        "openai": ["gpt-4o", "gpt-4o-mini", "o1", "o3-mini"],
        "google": ["gemini-2.0-flash", "gemini-2.0-pro", "gemini-1.5-pro"],
        "ollama": ["llama3.2", "llama3.1", "mistral", "qwen2.5", "phi4"],
    }
    models = known.get(backend, [])
    if not models:
        print(f"  no model list available for backend: {backend or '(unknown)'}")
        return
    print(f"  backend: {backend}")
    for m in models:
        print(f"    {m}")


def _cmd_endure(layout: Layout, args: list[str]) -> None:
    if not args:
        print("  usage: /endure list | approve <seq> | reject <seq> | sync [--remote]")
        return
    sub = args[0].lower()
    if sub == "list":
        _endure_list(layout)
    elif sub == "sync":
        _endure_sync(layout, "--remote" in args)
    else:
        print(f"  unknown endure subcommand: {sub}")


def _endure_list(layout: Layout) -> None:
    if not layout.operator_notifications_dir.exists():
        print("  no pending proposals")
        return
    found = False
    for f in sorted(layout.operator_notifications_dir.iterdir()):
        if "proposal_pending" in f.name:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                inner = data.get("data", {})
                seq = inner.get("ts", "?")
                content = str(inner.get("content", ""))
                preview = "".join(itertools.islice(content, 80)) + ("..." if len(content) > 80 else "")
                print(f"  [{seq}] {preview}")
                found = True
            except Exception:
                pass
    if not found:
        print("  no pending proposals")


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


# --- Debug ---

def _cmd_verbose(layout: Layout, args: list[str]) -> None:
    global _verbose, _debugger
    if args and args[0].lower() == "on":
        _verbose = True
    elif args and args[0].lower() == "off":
        _verbose = False
    else:
        _verbose = not _verbose
    if _verbose and _debugger is not None:
        _debugger = None
        print("  debugger: off (switched to verbose)")
    print(f"  verbose: {'on' if _verbose else 'off'}")


def _cmd_debugger(layout: Layout, args: list[str]) -> None:
    global _verbose, _debugger
    if not args or args[0].lower() == "off":
        _debugger = None
        print("  debugger: off")
        return
    if args[0].lower() == "on":
        flag = next((a for a in args[1:] if a.startswith("--")), None)
        mode = flag.lstrip("-") if flag else "chat"
        if mode not in ("all", "chat", "boot"):
            print("  usage: /debugger on [--all | --chat | --boot] | off")
            return
        _debugger = mode
        if _verbose:
            _verbose = False
            print("  verbose: off (switched to debugger)")
        print(f"  debugger: on --{mode}")
        return
    print("  usage: /debugger on [--all | --chat | --boot] | off")


def _cmd_help() -> None:
    print("""
  Platform commands:

  Entity & session:
    /status                      — entity status overview
    /doctor [--fix]              — check and optionally repair integrity
    /exit | /bye | /close        — close session

  Memory & inbox:
    /inbox [list]                — list system notifications
    /inbox view <n>              — view notification by index
    /inbox dismiss <n>           — remove notification by index
    /inbox clear                 — remove all notifications

  Workspace:
    /work set <subdir>           — set workspace focus
    /work clone <repo>           — clone repo and set as workspace focus

  Skills & execution:
    /skill list                  — list installed skills
    /skill audit <name>          — audit a skill

  Model & endure:
    /model                       — show current model and backend
    /model list                  — list known models for current backend
    /model <name>                — switch model mid-session (takes effect immediately)
    /endure list                 — list pending Evolution Proposals
    /endure sync [--remote]      — commit entity root to version control

  Debug:
    /verbose [on|off]            — toggle component message summary
    /debugger on [--all|--chat|--boot] | off
                                 — inspect CPE context (disables verbose)
                                   --chat: session history only
                                   --boot: system + instruction block only
                                   --all:  full context

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

def _sha256_str(s: str) -> str:
    import hashlib
    return hashlib.sha256(s.encode()).hexdigest()


def _write_evolution_auth(layout: Layout, content: str, auth_digest: str) -> None:
    ts = int(time.time() * 1000)
    envelope = acp_encode(
        env_type="MSG",
        source="operator",
        data={"type": "EVOLUTION_AUTH", "auth_digest": auth_digest, "ts": ts},
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
