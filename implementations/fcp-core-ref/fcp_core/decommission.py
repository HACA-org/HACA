"""
Decommission — FCP-Core §11.

Sequence:
  1. Write decommission flag (phase: "sleep")
  2. Run Sleep Cycle
  3. Update flag (phase: "dispose")
  4. Archive or destroy Entity Store
  5. Remove flag (archive) / flag is gone with the store (destroy)

Partial recovery: if decommission flag is present at boot, the decommission
was interrupted. Caller should call detect_partial() and resume_partial() or
restart from scratch.
"""

from __future__ import annotations

import shutil
import tarfile
import time
from pathlib import Path
from typing import TYPE_CHECKING

from .store import Layout, atomic_write, read_json

if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------------
# Flag helpers
# ---------------------------------------------------------------------------

def detect_partial(layout: Layout) -> dict | None:
    """Return the decommission flag contents if a partial decommission exists,
    otherwise None."""
    if not layout.decommission_flag.exists():
        return None
    try:
        return read_json(layout.decommission_flag)
    except Exception:
        return None


def _write_flag(layout: Layout, phase: str, mode: str) -> None:
    atomic_write(layout.decommission_flag, {
        "phase": phase,
        "mode": mode,
        "ts": time.time(),
    })


def _clear_flag(layout: Layout) -> None:
    try:
        layout.decommission_flag.unlink()
    except FileNotFoundError:
        pass


# ---------------------------------------------------------------------------
# Archive
# ---------------------------------------------------------------------------

def archive(layout: Layout) -> Path:
    """Create a tar.gz of the entity root.

    The archive is placed in the parent directory of the entity root with the
    name ``<entity_name>_<timestamp>.tar.gz``. An optional ``archive_path``
    key in the baseline overrides the destination directory.

    Returns the path of the created archive.
    """
    dest_dir = layout.root.parent
    try:
        baseline = read_json(layout.baseline)
        override = baseline.get("archive_path", "")
        if override:
            dest_dir = Path(override).expanduser().resolve()
            dest_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    ts = int(time.time())
    archive_name = f"{layout.root.name}_{ts}.tar.gz"
    archive_path = dest_dir / archive_name

    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(layout.root, arcname=layout.root.name)

    return archive_path


# ---------------------------------------------------------------------------
# Run decommission
# ---------------------------------------------------------------------------

def run(layout: Layout, mode: str, sleep_fn, partial: dict | None = None) -> None:
    """Execute the full decommission sequence.

    ``mode``     — "archive" or "destroy"
    ``sleep_fn`` — callable(); runs the Sleep Cycle
    ``partial``  — flag contents if resuming from a partial decommission
    """
    phase = partial.get("phase", "sleep") if partial else "sleep"

    if phase == "sleep":
        _write_flag(layout, "sleep", mode)
        sleep_fn()
        phase = "dispose"

    if phase == "dispose":
        _write_flag(layout, "dispose", mode)
        if mode == "archive":
            archive_path = archive(layout)
            _clear_flag(layout)
            print(f"[FCP-Core] Entity archived → {archive_path}")
        else:
            # destroy: flag is inside the tree — will be deleted with it
            shutil.rmtree(layout.root)
            print("[FCP-Core] Entity destroyed.")
