"""
Filesystem primitives for the FCP Entity Store.

All writes to .json files go through atomic_write().
All appends to .jsonl files go through append_jsonl().
Path constants are relative to the entity root (a Path passed at runtime).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Atomic I/O
# ---------------------------------------------------------------------------

def atomic_write(path: Path, data: dict[str, Any]) -> None:
    """Write *data* as JSON to *path* atomically (.tmp + rename)."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def read_json(path: Path) -> dict[str, Any]:
    """Read and parse a JSON file. Raises FileNotFoundError if absent."""
    return json.loads(path.read_text(encoding="utf-8"))


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    """Append *record* as a single JSON line to a .jsonl file."""
    line = json.dumps(record, separators=(",", ":")) + "\n"
    with path.open("a", encoding="utf-8") as f:
        f.write(line)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read all lines from a .jsonl file. Returns [] if file is absent."""
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            pass  # skip malformed lines
    return records


# ---------------------------------------------------------------------------
# Entity root layout  (§2.1)
# All paths are relative to the entity root and returned as Path objects.
# ---------------------------------------------------------------------------

class Layout:
    """Resolved absolute paths for every named location in the Entity Store."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    # -- top-level structural content (Endure scope) --
    @property
    def boot_md(self) -> Path:
        return self.root / "boot.md"

    @property
    def persona_dir(self) -> Path:
        return self.root / "persona"

    @property
    def skills_dir(self) -> Path:
        return self.root / "skills"

    @property
    def skills_lib_dir(self) -> Path:
        return self.root / "skills" / "lib"

    @property
    def skills_index(self) -> Path:
        return self.root / "skills" / "index.json"

    @property
    def hooks_dir(self) -> Path:
        return self.root / "hooks"

    # -- workspace (outside Endure scope) --
    @property
    def workspace_dir(self) -> Path:
        return self.root / "workspace"

    @property
    def workspace_stage_dir(self) -> Path:
        return self.root / "workspace" / "stage"

    # -- io --
    @property
    def inbox_dir(self) -> Path:
        return self.root / "io" / "inbox"

    @property
    def presession_dir(self) -> Path:
        return self.root / "io" / "inbox" / "presession"

    @property
    def spool_dir(self) -> Path:
        return self.root / "io" / "spool"

    # -- memory (MIL exclusive write territory) --
    @property
    def memory_dir(self) -> Path:
        return self.root / "memory"

    @property
    def imprint(self) -> Path:
        return self.root / "memory" / "imprint.json"

    @property
    def episodic_dir(self) -> Path:
        return self.root / "memory" / "episodic"

    @property
    def semantic_dir(self) -> Path:
        return self.root / "memory" / "semantic"

    @property
    def active_context_dir(self) -> Path:
        return self.root / "memory" / "active_context"

    @property
    def session_store(self) -> Path:
        return self.root / "memory" / "session.jsonl"

    @property
    def working_memory(self) -> Path:
        return self.root / "memory" / "working-memory.json"

    @property
    def session_handoff(self) -> Path:
        return self.root / "memory" / "session-handoff.json"

    # -- state (SIL territory) --
    @property
    def state_dir(self) -> Path:
        return self.root / "state"

    @property
    def baseline(self) -> Path:
        return self.root / "state" / "baseline.json"

    @property
    def integrity_doc(self) -> Path:
        return self.root / "state" / "integrity.json"

    @property
    def integrity_log(self) -> Path:
        return self.root / "state" / "integrity.log"

    @property
    def integrity_chain(self) -> Path:
        return self.root / "state" / "integrity_chain.jsonl"

    @property
    def drift_probes(self) -> Path:
        return self.root / "state" / "drift-probes.jsonl"

    @property
    def semantic_digest(self) -> Path:
        return self.root / "state" / "semantic-digest.json"

    @property
    def workspace_focus(self) -> Path:
        return self.root / "state" / "workspace_focus.json"

    @property
    def pending_closure(self) -> Path:
        return self.root / "state" / "pending-closure.json"

    @property
    def sentinels_dir(self) -> Path:
        return self.root / "state" / "sentinels"

    @property
    def session_token(self) -> Path:
        return self.root / "state" / "sentinels" / "session.token"

    @property
    def snapshots_dir(self) -> Path:
        return self.root / "state" / "snapshots"

    @property
    def operator_notifications_dir(self) -> Path:
        return self.root / "state" / "operator_notifications"

    @property
    def distress_beacon(self) -> Path:
        return self.root / "state" / "distress.beacon"

    @property
    def decommission_flag(self) -> Path:
        return self.root / "state" / "decommission.json"

    # -- helpers --
    def skill_manifest(self, name: str, builtin: bool = False) -> Path:
        if builtin:
            return self.root / "skills" / "lib" / name / "manifest.json"
        return self.root / "skills" / name / "manifest.json"

    def snapshot_dir(self, seq: int) -> Path:
        return self.root / "state" / "snapshots" / str(seq)

    def volatile_dirs(self) -> list[Path]:
        """Directories that must exist at runtime but are not tracked by the
        Integrity Document. Recreated by /doctor --fix if absent."""
        return [
            self.inbox_dir,
            self.presession_dir,
            self.spool_dir,
            self.sentinels_dir,
            self.snapshots_dir,
            self.operator_notifications_dir,
            self.workspace_stage_dir,
            self.active_context_dir,
        ]
