"""
Operator Interface — FCP-Core §12.

§12.2  Interactive loop (input → inject as MSG → session cycle)
§12.3.1 Platform commands (/status, /doctor, /model, /endure, /inbox, /work, /skill, /verbose)
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
# Notification display
# ---------------------------------------------------------------------------

def present_notifications(layout: Layout) -> None:
    """Print and clear pending operator notifications."""
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
    """Display pending Evolution Proposals; collect Operator approve/reject decisions.

    Returns list of authorized proposals (approved by Operator).
    """
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

def handle_platform_command(layout: Layout, line: str) -> bool:
    """Handle a /command line. Returns True if handled, False if unknown."""
    parts = line.strip().split()
    if not parts:
        return False
    cmd = parts[0].lower()
    args = list(itertools.islice(parts, 1, len(parts)))

    if cmd == "/status":
        _cmd_status(layout)
        return True
    if cmd == "/doctor":
        _cmd_doctor(layout, args)
        return True
    if cmd == "/model":
        _cmd_model(layout, args)
        return True
    if cmd == "/endure":
        _cmd_endure(layout, args)
        return True
    if cmd == "/inbox":
        _cmd_inbox(layout)
        return True
    if cmd == "/work":
        _cmd_work(layout, args)
        return True
    if cmd == "/skill":
        _cmd_skill(layout, args)
        return True
    if cmd == "/verbose":
        _cmd_verbose(layout)
        return True
    if cmd == "/help":
        _cmd_help()
        return True
    return False


def _cmd_status(layout: Layout) -> None:
    token_present = layout.session_token.exists()
    session_size = layout.session_store.stat().st_size if layout.session_store.exists() else 0
    beacon = layout.distress_beacon.exists()
    print(f"  session token : {'active' if token_present else 'inactive'}")
    print(f"  session store : {session_size} bytes")
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

    # Repair volatile dirs first if --fix requested
    if fix:
        for d in layout.volatile_dirs():
            if not d.exists():
                d.mkdir(parents=True, exist_ok=True)
                print(f"  created: {d.relative_to(layout.root)}")

    findings = run_all(layout)
    print_report(findings)

    failed = [f for f in findings if not f.passed]
    if failed:
        print(f"\n  {len(failed)} issue(s) found. Run /doctor --fix to repair volatile dirs.")


def _cmd_model(layout: Layout, args: list[str]) -> None:
    if not args:
        try:
            baseline = read_json(layout.baseline)
            model = baseline.get("cpe", {}).get("model", "(not set)")
            print(f"  current model: {model}")
        except Exception:
            print("  could not read baseline")
        return
    print("  /model change requires an Endure cycle — use /endure to queue a proposal")


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
    cmd = ["git", "add", "-A"]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(layout.root))
    if r.returncode != 0:
        print(f"  git add failed: {r.stderr.strip()}")
        return
    ts = int(time.time())
    r2 = subprocess.run(
        ["git", "commit", "-m", f"endure sync {ts}"],
        capture_output=True, text=True, cwd=str(layout.root)
    )
    if r2.returncode != 0:
        print(f"  git commit: {r2.stderr.strip() or 'nothing to commit'}")
    else:
        print(f"  committed: {r2.stdout.strip()}")
    if remote:
        r3 = subprocess.run(
            ["git", "push", "origin"],
            capture_output=True, text=True, cwd=str(layout.root)
        )
        print(f"  push: {'ok' if r3.returncode == 0 else r3.stderr.strip()}")


def _cmd_inbox(layout: Layout) -> None:
    if not layout.presession_dir.exists():
        print("  inbox empty")
        return
    files = list(layout.presession_dir.iterdir())
    if not files:
        print("  inbox empty")
        return
    for f in sorted(files):
        print(f"  {f.name}")


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
        r = subprocess.run(["git", "clone", repo, str(dest)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            print(f"  clone failed: {r.stderr.strip()}")
            return
        atomic_write(layout.workspace_focus, {"path": str(dest)})
        print(f"  cloned and focus set: {dest}")
    else:
        print("  usage: /work set <subdir> | clone <repo>")


def _cmd_skill(layout: Layout, args: list[str]) -> None:
    if not args:
        print("  usage: /skill audit <name> | list")
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
        print("  usage: /skill audit <name> | list")


def _cmd_verbose(layout: Layout) -> None:
    print("  verbose mode toggled (no persistent state in this implementation)")


def _cmd_help() -> None:
    print("""
  Platform commands:
    /status              — entity status overview
    /doctor [--fix]      — check and optionally repair volatile dirs
    /model               — show current CPE model
    /endure list         — list pending Evolution Proposals
    /endure sync [--remote] — commit entity root to version control
    /inbox               — list pre-session buffer contents
    /work set <subdir>   — set workspace focus
    /work clone <repo>   — clone repo and set as workspace focus
    /skill list          — list installed skills
    /skill audit <name>  — audit a skill
    /verbose             — toggle verbose mode
    /help                — this message
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
