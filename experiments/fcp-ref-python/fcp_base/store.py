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


def load_baseline(layout: "Layout") -> dict[str, Any]:
    """Read baseline.json, returning {} on any error."""
    try:
        return read_json(layout.baseline)
    except Exception:
        return {}


def load_agenda(layout: "Layout") -> dict[str, Any]:
    """Read state/agenda.json, returning {"tasks": []} on any error."""
    try:
        return read_json(layout.agenda)
    except Exception:
        return {"tasks": []}


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

    # -- skill staging (outside entity root, accessible via workspace_focus) --
    @property
    def workspace_stage_dir(self) -> Path:
        return Path("/tmp") / "fcp-stage" / self.root.name

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
    def agenda(self) -> Path:
        return self.root / "state" / "agenda.json"

    @property
    def last_session(self) -> Path:
        return self.root / "state" / "last_session.json"

    @property
    def first_stimuli(self) -> Path:
        return self.root / "state" / "first-stimuli.json"

    @property
    def distress_beacon(self) -> Path:
        return self.root / "state" / "distress.beacon"

    @property
    def decommission_flag(self) -> Path:
        return self.root / "state" / "decommission.json"

    # -- cmi (state territory) --
    @property
    def cmi_dir(self) -> Path:
        return self.root / "state" / "cmi"

    @property
    def cmi_credential(self) -> Path:
        return self.root / "state" / "cmi" / "credential.json"

    @property
    def cmi_channels_dir(self) -> Path:
        return self.root / "state" / "cmi" / "channels"

    def cmi_channel_dir(self, chan_id: str) -> Path:
        return self.root / "state" / "cmi" / "channels" / chan_id

    def cmi_blackboard(self, chan_id: str) -> Path:
        return self.root / "state" / "cmi" / "channels" / chan_id / "blackboard.jsonl"

    def cmi_participants(self, chan_id: str) -> Path:
        return self.root / "state" / "cmi" / "channels" / chan_id / "participants.json"

    def cmi_enrollment(self, chan_id: str) -> Path:
        return self.root / "state" / "cmi" / "channels" / chan_id / "enrollment.json"

    def cmi_close_token(self, chan_id: str) -> Path:
        return self.root / "state" / "cmi" / "channels" / chan_id / "close_token.json"

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

# ---------------------------------------------------------------------------
# API Keys & Environment Management
# ---------------------------------------------------------------------------

API_KEY_ENV: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "google": "GOOGLE_API_KEY",
}


def load_env_file() -> None:
    """Load KEY=value pairs from ~/.fcp.env into os.environ (no-op if absent)."""
    env_file = Path.home() / ".fcp.env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        # Fallback to file value if shell env is empty or missing
        if key and not os.environ.get(key):
            os.environ[key] = val.strip()


# ---------------------------------------------------------------------------
# Global FCP config  (~/.fcp/config.json)
# ---------------------------------------------------------------------------

FCP_HOME = Path.home() / ".fcp"
FCP_ENTITIES_DIR = FCP_HOME / "entities"
_FCP_CONFIG = FCP_HOME / "config.json"


def get_default_entity() -> str | None:
    """Return the default entity_id from ~/.fcp/config.json, or None."""
    try:
        return read_json(_FCP_CONFIG).get("default")
    except Exception:
        return None


def set_default_entity(entity_id: str) -> None:
    """Write entity_id as the default in ~/.fcp/config.json."""
    FCP_HOME.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = {}
    try:
        data = read_json(_FCP_CONFIG)
    except Exception:
        pass
    data["default"] = entity_id
    atomic_write(_FCP_CONFIG, data)


def list_entities() -> list[str]:
    """Return entity_ids found under ~/.fcp/entities/ (dirs containing .fcp-entity)."""
    if not FCP_ENTITIES_DIR.exists():
        return []
    return sorted(
        d.name for d in FCP_ENTITIES_DIR.iterdir()
        if d.is_dir() and (d / ".fcp-entity").exists()
    )


def entity_root_for(entity_id: str) -> Path:
    """Return the entity root path for a given entity_id."""
    return FCP_ENTITIES_DIR / entity_id


def save_api_key(entity_name: str, env_var: str, api_key: str) -> None:
    """Append or update KEY=value in ~/.fcp.env."""
    env_file = Path.home() / ".fcp.env"
    lines: list[str] = []
    if env_file.exists():
        lines = env_file.read_text(encoding="utf-8").splitlines()

    found = False
    new_lines = []
    for line in lines:
        if line.strip().startswith(f"{env_var}="):
            new_lines.append(f"{env_var}={api_key}")
            found = True
        else:
            new_lines.append(line)

    if not found:
        new_lines.append(f"{env_var}={api_key}")

    env_file.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    env_file.chmod(0o600)
    load_env_file()  # Refresh current process
