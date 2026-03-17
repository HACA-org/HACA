#!/usr/bin/env python3
"""core/mil.py — Memory Interface Layer."""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from .config import Config


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_json_atomic(path: Path, obj: dict):
    tmp = str(path) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=2)
    os.replace(tmp, str(path))


class MIL:
    def __init__(self, root: Path, config: Config):
        self.root = root
        self.config = config

        self.session_file = root / "memory" / "session.jsonl"
        self.agenda_file = root / "state" / "agenda.jsonl"
        self.episodic_dir = root / "memory" / "episodic"
        self.active_ctx_dir = root / "memory" / "active_context"
        self.working_memory = root / "memory" / "working-memory.json"
        self.session_handoff = root / "memory" / "session-handoff.json"
        self.presession_dir = root / "memory" / "inbox" / "presession"
        self.inbox_dir = root / "memory" / "inbox"
        self.spool_dir = root / "memory" / "spool"

    def drain(self) -> tuple:
        self.inbox_dir.mkdir(parents=True, exist_ok=True)
        self.presession_dir.mkdir(parents=True, exist_ok=True)

        count_session = 0
        count_agenda = 0

        # Inject pre-session buffer first (FIFO)
        for msg in sorted(self.presession_dir.glob("*.msg")):
            try:
                with open(self.session_file, "a") as f:
                    f.write(msg.read_text())
                    if not msg.read_text().endswith("\n"):
                        f.write("\n")
                msg.unlink()
                count_session += 1
            except Exception as e:
                print(f"[MIL] DRAIN error (presession): {e}", file=sys.stderr)

        # Drain main inbox
        for msg in sorted(self.inbox_dir.glob("*.msg")):
            try:
                content = msg.read_text().strip()
                if not content:
                    msg.unlink()
                    continue
                env_type = ""
                try:
                    env_type = json.loads(content).get("type", "")
                except Exception:
                    pass

                target = self.agenda_file if env_type == "SCHEDULE" else self.session_file
                with open(target, "a") as f:
                    f.write(content + "\n")
                msg.unlink()

                if env_type == "SCHEDULE":
                    count_agenda += 1
                else:
                    count_session += 1
            except Exception as e:
                print(f"[MIL] DRAIN error: {e}", file=sys.stderr)

        if count_session > 0:
            print(f"[MIL] DRAIN: {count_session} msgs → session.jsonl", file=sys.stderr)
        if count_agenda > 0:
            print(f"[MIL] DRAIN: {count_agenda} msgs → agenda.jsonl", file=sys.stderr)

        return count_session, count_agenda

    def stage1_consolidate(self):
        print("[MIL] Stage 1: Memory Consolidation...", file=sys.stderr)
        self.episodic_dir.mkdir(parents=True, exist_ok=True)
        self.working_memory.parent.mkdir(parents=True, exist_ok=True)

        self.drain()

        if not self.session_file.exists() or self.session_file.stat().st_size == 0:
            print("[MIL] Stage 1: No session data to archive.", file=sys.stderr)
        else:
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
            fragment = self.episodic_dir / f"session_{ts}.jsonl"
            import shutil
            shutil.copy2(self.session_file, fragment)
            self.session_file.write_text("")
            print(f"[MIL] Stage 1: Session archived → {fragment}", file=sys.stderr)

            self.apply_closure_payload(fragment)
            self._update_working_memory(fragment)

        if not self.session_handoff.exists():
            handoff = {
                "version": "1.0",
                "updated_at": _ts(),
                "pending_tasks": [],
                "next_steps": [],
                "notes": "No explicit session handoff from CPE.",
            }
            _write_json_atomic(self.session_handoff, handoff)
            print("[MIL] Stage 1: Placeholder Session Handoff written.", file=sys.stderr)

        print("[MIL] Stage 1: Memory Consolidation complete.", file=sys.stderr)

    def stage2_gc(self):
        print("[MIL] Stage 2: Garbage Collection...", file=sys.stderr)

        # Remove stale active_context symlinks
        if self.active_ctx_dir.is_dir():
            stale = 0
            for link in self.active_ctx_dir.iterdir():
                if link.name.startswith("."):
                    continue
                if link.is_symlink() and not link.exists():
                    link.unlink()
                    stale += 1
            if stale > 0:
                print(f"[MIL] Stage 2: Removed {stale} stale active_context symlinks.", file=sys.stderr)

        # Clean spool/*.tmp older than 2 days
        if self.spool_dir.is_dir():
            import time
            cutoff = time.time() - 2 * 86400
            for tmp in self.spool_dir.rglob("*.tmp"):
                try:
                    if tmp.stat().st_mtime < cutoff:
                        tmp.unlink()
                except Exception:
                    pass

        # Clean presession/*.msg older than 7 days
        if self.presession_dir.is_dir():
            import time
            cutoff = time.time() - 7 * 86400
            for msg in self.presession_dir.glob("*.msg"):
                try:
                    if msg.stat().st_mtime < cutoff:
                        msg.unlink()
                except Exception:
                    pass

        # session.jsonl size check
        if self.session_file.exists():
            size = self.session_file.stat().st_size
            if size > self.config.S_bytes:
                print(
                    f"[MIL] Stage 2: WARNING: session.jsonl is {size} bytes "
                    f"(> S_bytes={self.config.S_bytes}). Consider session summarization.",
                    file=sys.stderr,
                )

        print("[MIL] Stage 2: Garbage Collection complete.", file=sys.stderr)

    def read_context(self, budget: int) -> str:
        if not self.session_file.exists():
            return ""
        lines = []
        with open(self.session_file, errors="replace") as f:
            for line in f:
                line = line.rstrip("\n")
                if line:
                    lines.append(line)
        lines.reverse()
        used = 0
        result = []
        for line in lines:
            if used + len(line) + 1 > budget:
                break
            result.append(line)
            used += len(line) + 1
        return "\n".join(result)

    def apply_closure_payload(self, fragment_path: Path):
        wm_entries = []
        handoff_data = None
        consolidation = ""

        try:
            with open(fragment_path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        env = json.loads(line)
                        if env.get("type") != "CLOSURE_PAYLOAD":
                            continue
                        data_raw = env.get("data", "{}")
                        data = json.loads(data_raw) if isinstance(data_raw, str) else data_raw
                        wm_entries = data.get("working_memory", [])
                        handoff_data = data.get("session_handoff", None)
                        consolidation = data.get("consolidation_content", "")
                    except Exception:
                        pass
        except Exception:
            pass

        if handoff_data:
            record = {
                "version": "1.0",
                "updated_at": _ts(),
                "pending_tasks": handoff_data.get("pending_tasks", []),
                "next_steps": handoff_data.get("next_steps", []),
                "notes": handoff_data.get("notes", ""),
            }
            _write_json_atomic(self.session_handoff, record)
            print("[MIL] Stage 1: Session Handoff written from Closure Payload.", file=sys.stderr)

        if wm_entries:
            try:
                wm = json.loads(self.working_memory.read_text()) if self.working_memory.exists() else {"version": "1.0", "entries": []}
            except Exception:
                wm = {"version": "1.0", "entries": []}
            existing_paths = {e["path"] for e in wm.get("entries", [])}
            added = 0
            for entry in wm_entries:
                raw_path = entry.get("path", "")
                if not raw_path:
                    continue
                abs_path = raw_path if os.path.isabs(raw_path) else str(self.root / raw_path)
                if not os.path.exists(abs_path):
                    print(f"[MIL] Stage 1: WM entry dropped (absent): {raw_path}", file=sys.stderr)
                    continue
                if abs_path not in existing_paths:
                    wm["entries"].append({"priority": entry.get("priority", 50), "path": abs_path})
                    existing_paths.add(abs_path)
                    added += 1
            wm["entries"].sort(key=lambda e: e.get("priority", 50))
            if len(wm["entries"]) > 20:
                wm["entries"] = wm["entries"][:20]
            _write_json_atomic(self.working_memory, wm)
            print(f"[MIL] Stage 1: Working Memory updated ({added} new entries).", file=sys.stderr)

        if consolidation:
            envelope = {"actor": "cpe", "type": "CONSOLIDATION", "ts": _ts(),
                        "data": json.dumps({"content": consolidation})}
            with open(self.session_file, "a") as f:
                json.dump(envelope, f)
                f.write("\n")
            print("[MIL] Stage 1: Consolidation content written to session.jsonl.", file=sys.stderr)

    def _update_working_memory(self, fragment_path: Path):
        try:
            wm = json.loads(self.working_memory.read_text()) if self.working_memory.exists() else {"version": "1.0", "entries": []}
        except Exception:
            wm = {"version": "1.0", "entries": []}

        entries = wm.get("entries", [])
        existing = {e["path"] for e in entries}
        abs_path = str(fragment_path)
        if abs_path not in existing:
            entries.append({"priority": 50, "path": abs_path})
        if len(entries) > 20:
            entries = entries[-20:]
        wm["entries"] = entries
        _write_json_atomic(self.working_memory, wm)
        self.rebuild_active_context()

    def rebuild_active_context(self):
        if not self.working_memory.exists():
            return
        self.active_ctx_dir.mkdir(parents=True, exist_ok=True)

        # Remove existing symlinks
        for entry in self.active_ctx_dir.iterdir():
            if entry.name.startswith("."):
                continue
            if entry.is_symlink():
                entry.unlink()

        try:
            wm = json.loads(self.working_memory.read_text())
        except Exception:
            return

        for item in wm.get("entries", []):
            src = item.get("path", "")
            if not src or not os.path.exists(src):
                continue
            priority = item.get("priority", 50)
            basename = os.path.basename(src)
            link_name = f"{priority:03d}-{basename}"
            link_path = self.active_ctx_dir / link_name
            rel = os.path.relpath(src, str(self.active_ctx_dir))
            try:
                link_path.symlink_to(rel)
            except FileExistsError:
                pass

        print("[MIL] Stage 1: active_context/ symlinks rebuilt from Working Memory.", file=sys.stderr)
