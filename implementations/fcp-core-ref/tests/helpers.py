"""Shared test helpers — create minimal entity root fixtures."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from fcp_core.store import Layout


def make_layout() -> tuple[Layout, Path]:
    """Create a temp dir with full entity structure. Returns (layout, tmpdir)."""
    tmp = Path(tempfile.mkdtemp())
    layout = Layout(tmp)

    dirs = [
        tmp / "persona",
        tmp / "skills" / "lib",
        tmp / "hooks",
        tmp / "workspace" / "stage",
        tmp / "io" / "inbox" / "presession",
        tmp / "io" / "spool",
        tmp / "memory" / "episodic",
        tmp / "memory" / "semantic",
        tmp / "memory" / "active_context",
        tmp / "state" / "sentinels",
        tmp / "state" / "snapshots",
        tmp / "state" / "operator_notifications",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)

    # minimal boot.md
    (tmp / "boot.md").write_text("# Boot Protocol\n", encoding="utf-8")

    # minimal persona
    (tmp / "persona" / "00-base.md").write_text("You are a helpful assistant.\n", encoding="utf-8")

    # minimal baseline
    baseline: dict[str, Any] = {
        "version": "1.0.0",
        "profile": "HACA-Core",
        "cpe": {"backend": "ollama", "model": "llama3.2", "topology": "transparent"},
        "context_budget": {"session_critical_threshold": 100000},
        "session_store": {"rotation_threshold_bytes": 1000000},
        "working_memory": {"max_entries": 50},
        "heartbeat": {"interval_seconds": 30, "cycle_threshold": 10},
        "watchdog": {"sil_threshold_seconds": 25},
        "fault": {"n_retry": 3, "n_boot": 3, "n_channel": 3},
        "integrity_chain": {"checkpoint_interval": 10},
    }
    _atomic_write(tmp / "state" / "baseline.json", baseline)

    # empty skills index
    _atomic_write(tmp / "skills" / "index.json", {
        "version": "1.0.0",
        "skills": [],
        "aliases": {},
    })

    # minimal integrity doc
    _atomic_write(tmp / "state" / "integrity.json", {
        "version": "1.0.0",
        "genesis_omega": "0" * 64,
        "files": {},
        "last_checkpoint": None,
    })

    # empty integrity chain
    (tmp / "state" / "integrity_chain.jsonl").write_text("", encoding="utf-8")

    # empty integrity log
    (tmp / "state" / "integrity.log").write_text("", encoding="utf-8")

    # empty session store
    (tmp / "memory" / "session.jsonl").write_text("", encoding="utf-8")

    # minimal imprint
    _atomic_write(tmp / "memory" / "imprint.json", {
        "entity_id": "test",
        "genesis_omega": "0" * 64,
    })

    # empty working memory
    _atomic_write(tmp / "memory" / "working-memory.json", {"entries": []})

    return layout, tmp


def _atomic_write(path: Path, data: dict[str, Any]) -> None:
    import os
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)
