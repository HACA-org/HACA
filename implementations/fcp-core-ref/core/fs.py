"""POSIX filesystem primitives for FCP-Core.

All writes go through this module to enforce the file-format contracts
defined in FCP-Core §2.2:
  - .json  → atomic (write .tmp sibling, then rename(2) into place)
  - .jsonl → append-only (open 'a', write one JSON line + newline)
  - .msg   → spool-then-rename (write to io/spool/, rename to io/inbox/)
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# JSON  – atomic writes (§2.2)
# ---------------------------------------------------------------------------

def atomic_write_json(path: str | Path, data: Any) -> None:
    """Write *data* to *path* atomically using a .tmp sibling + rename(2).

    The serialised JSON is written to ``<path>.tmp`` first; on success the
    temporary file is renamed over the target.  If the write or rename fails
    the original target (if any) is left untouched.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.rename(tmp, path)          # POSIX rename(2) — atomic on same filesystem
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def read_json(path: str | Path) -> Any:
    """Read and parse a JSON file.  Raises FileNotFoundError if absent."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# JSONL  – append-only writes (§2.2)
# ---------------------------------------------------------------------------

def append_jsonl(path: str | Path, obj: Any) -> None:
    """Append *obj* as a single JSON line to the .jsonl file at *path*.

    The file is created if it does not exist.  The directory tree is created
    automatically.  Each call produces exactly one complete JSON line followed
    by a newline character.  Existing lines are never modified.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def read_jsonl(path: str | Path) -> list[Any]:
    """Read all lines from a .jsonl file and return them as a list.

    Returns an empty list if the file does not exist.  Malformed lines are
    silently skipped (they cannot be consumed but do not break the reader).
    """
    path = Path(path)
    if not path.exists():
        return []
    results: list[Any] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            results.append(json.loads(raw))
        except json.JSONDecodeError:
            pass
    return results


# ---------------------------------------------------------------------------
# .msg  – spool-then-rename pattern (§3.1)
# ---------------------------------------------------------------------------

def spool_msg(entity_root: str | Path, envelope: dict[str, Any]) -> Path:
    """Write *envelope* as a .msg file via the spool-then-rename pattern.

    Steps:
      1. Write JSON to ``io/spool/<uuid>.msg.tmp``
      2. ``os.rename()`` to ``io/inbox/<uuid>.msg``

    Returns the final inbox path so callers can record where the message
    landed (useful for debugging; the file is consumed by FCP at cycle start).
    """
    entity_root = Path(entity_root)
    spool_dir = entity_root / "io" / "spool"
    inbox_dir = entity_root / "io" / "inbox"
    spool_dir.mkdir(parents=True, exist_ok=True)
    inbox_dir.mkdir(parents=True, exist_ok=True)

    msg_id = uuid.uuid4().hex
    tmp_path = spool_dir / f"{msg_id}.msg.tmp"
    final_path = inbox_dir / f"{msg_id}.msg"

    try:
        tmp_path.write_text(
            json.dumps(envelope, ensure_ascii=False), encoding="utf-8"
        )
        os.rename(tmp_path, final_path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise

    return final_path


def spool_presession_msg(entity_root: str | Path, envelope: dict[str, Any]) -> Path:
    """Like :func:`spool_msg` but targets ``io/inbox/presession/``."""
    entity_root = Path(entity_root)
    spool_dir = entity_root / "io" / "spool"
    presession_dir = entity_root / "io" / "inbox" / "presession"
    spool_dir.mkdir(parents=True, exist_ok=True)
    presession_dir.mkdir(parents=True, exist_ok=True)

    msg_id = uuid.uuid4().hex
    tmp_path = spool_dir / f"{msg_id}.msg.tmp"
    final_path = presession_dir / f"{msg_id}.msg"

    try:
        tmp_path.write_text(
            json.dumps(envelope, ensure_ascii=False), encoding="utf-8"
        )
        os.rename(tmp_path, final_path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise

    return final_path


# ---------------------------------------------------------------------------
# Inbox drain (§6.1)
# ---------------------------------------------------------------------------

def drain_inbox(entity_root: str | Path) -> list[dict[str, Any]]:
    """Read all .msg files from ``io/inbox/`` in arrival order.

    Each file is parsed, appended to the result list, and then **deleted**.
    The arrival order heuristic is file creation time (``st_ctime``) falling
    back to filename lexicographic order when timestamps are identical.

    The presession sub-directory is NOT drained here; it is handled
    separately during Boot Phase 5 context assembly (§5.1).

    Returns:
        List of parsed envelope dicts in arrival order.
    """
    entity_root = Path(entity_root)
    inbox_dir = entity_root / "io" / "inbox"
    inbox_dir.mkdir(parents=True, exist_ok=True)

    msg_files = sorted(
        [p for p in inbox_dir.iterdir() if p.is_file() and p.suffix == ".msg"],
        key=lambda p: (p.stat().st_ctime, p.name),
    )

    envelopes: list[dict[str, Any]] = []
    for msg_file in msg_files:
        try:
            raw = msg_file.read_text(encoding="utf-8")
            obj = json.loads(raw)
            envelopes.append(obj)
        except (OSError, json.JSONDecodeError):
            pass  # Malformed .msg — skip but leave; SIL handles at Vital Check
        finally:
            msg_file.unlink(missing_ok=True)

    return envelopes


def drain_presession(entity_root: str | Path) -> list[dict[str, Any]]:
    """Drain the presession buffer (``io/inbox/presession/``) in FIFO order.

    Returns envelopes in arrival order.  Files are deleted after reading.
    Used at Boot Phase 5 to inject pre-session stimuli before the first cycle.
    """
    entity_root = Path(entity_root)
    presession_dir = entity_root / "io" / "inbox" / "presession"
    if not presession_dir.exists():
        return []

    msg_files = sorted(
        [p for p in presession_dir.iterdir() if p.is_file() and p.suffix == ".msg"],
        key=lambda p: (p.stat().st_ctime, p.name),
    )

    envelopes: list[dict[str, Any]] = []
    for msg_file in msg_files:
        try:
            obj = json.loads(msg_file.read_text(encoding="utf-8"))
            envelopes.append(obj)
        except (OSError, json.JSONDecodeError):
            pass
        finally:
            msg_file.unlink(missing_ok=True)

    return envelopes


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def ensure_dirs(entity_root: str | Path) -> None:
    """Create the full FCP entity directory tree under *entity_root*.

    Creates all directories defined in §2.1.  Safe to call on an existing
    entity root; already-present directories are left untouched.
    """
    root = Path(entity_root)
    dirs = [
        root / "persona",
        root / "skills",
        root / "hooks",
        root / "io" / "inbox" / "presession",
        root / "io" / "spool",
        root / "memory" / "episodic",
        root / "memory" / "semantic",
        root / "memory" / "active_context",
        root / "state" / "sentinels",
        root / "state" / "operator_notifications",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)


def utcnow_iso() -> str:
    """Return current UTC time as ISO 8601 string (Z suffix)."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
