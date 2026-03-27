"""Shared test helpers — create minimal entity root fixtures."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from fcp_base.store import Layout


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
        "entity_id": "test-entity",
        "profile": "haca-core",
        "haca_profile": "HACA-Core-1.0.0",
        "cpe": {"backend": "ollama", "model": "llama3.2", "topology": "transparent"},
        "context_window": {"budget_pct": 80, "critical_pct": 80},
        "context_budget": {"session_critical_threshold": 100000},
        "drift": {"comparison_mechanism": "hash", "threshold": 0.0},
        "session_store": {"rotation_threshold_bytes": 1000000},
        "working_memory": {"max_entries": 50},
        "heartbeat": {"interval_seconds": 30, "cycle_threshold": 10},
        "watchdog": {"sil_threshold_seconds": 25},
        "fault": {"n_retry": 3, "n_boot": 3, "n_channel": 3},
        "integrity_chain": {"checkpoint_interval": 10},
        "pre_session_buffer": {"max_entries": 20},
        "operator_channel": {"notifications_dir": "state/operator_notifications"},
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

    # minimal valid imprint
    _atomic_write(tmp / "memory" / "imprint.json", {
        "version": "1.0",
        "activated_at": "2000-01-01T00:00:00Z",
        "haca_arch_version": "1.0.0",
        "haca_profile": "HACA-Core-1.0.0",
        "operator_bound": {
            "operator_name": "Test Operator",
            "operator_email": "test@example.com",
            "operator_hash": "0" * 64,
        },
        "structural_baseline": "0" * 64,
        "integrity_document": "0" * 64,
        "skills_index": "0" * 64,
    })

    # empty working memory
    _atomic_write(tmp / "memory" / "working-memory.json", {"entries": []})

    return layout, tmp


def make_evolve_layout(scope: dict[str, Any] | None = None) -> tuple[Layout, Path]:
    """Create a temp dir with a HACA-Evolve entity structure. Returns (layout, tmpdir)."""
    layout, tmp = make_layout()
    evolve_scope = scope or {
        "autonomous_evolution": True,
        "autonomous_skills": True,
        "cmi_access": "both",
        "operator_memory": True,
        "renewal_days": 30,
    }
    baseline_path = tmp / "state" / "baseline.json"
    with open(baseline_path, encoding="utf-8") as f:
        import json as _json
        baseline = _json.load(f)
    baseline["profile"] = "haca-evolve"
    baseline["drift"] = {"comparison_mechanism": "hash", "threshold": 0.15}
    baseline["evolve"] = {"scope": evolve_scope}
    _atomic_write(baseline_path, baseline)
    return layout, tmp


def _atomic_write(path: Path, data: dict[str, Any]) -> None:
    import os
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)
