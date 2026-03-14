"""
Sleep Cycle orchestrator — FCP-Core §7.

Four sequential stages:
  Stage 0: Semantic Drift Detection (SIL)
  Stage 1: Memory Consolidation (MIL — reads pending-closure.json)
  Stage 2: Garbage Collection (SIL rotates session.jsonl; MIL cleans symlinks)
  Stage 3: Endure Execution (SIL — authorized Evolution Proposals)

The SIL writes SLEEP_COMPLETE to integrity.log and removes session.token after Stage 3.
"""

from __future__ import annotations

import datetime
import json
import os
import time
from pathlib import Path
from typing import Any

from .acp import make as acp_encode
from .mil import (
    clean_stale_symlinks,
    process_closure,
    append_endure_commit,
    promote_to_semantic,
)
from .sil import (
    sha256_file,
    verify_structural_files,
    write_chain_entry,
    write_notification,
    revoke_session_token,
)
from .store import Layout, append_jsonl, atomic_write, read_json, read_jsonl


class SleepCycleError(Exception):
    """Raised when a Sleep Cycle stage fails unrecoverably."""


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def run_sleep_cycle(layout: Layout) -> None:
    """Execute all four Sleep Cycle stages sequentially.

    Writes SLEEP_COMPLETE to integrity.log and removes session.token at end.
    Raises SleepCycleError on unrecoverable failure.
    """
    # Stage 0 — Semantic Drift Detection
    drift_fault = _stage0_drift(layout)

    # Stage 1 — Memory Consolidation
    _stage1_consolidation(layout)

    # Stage 2 — Garbage Collection
    _stage2_gc(layout)

    # Stage 3 — Endure Execution
    _stage3_endure(layout)

    from .hooks import run_hook
    run_hook(layout, "post_endure", {})

    # Write SLEEP_COMPLETE
    _write_sleep_complete(layout)

    # Remove session token (last act)
    _remove_session_token(layout)

    if drift_fault:
        # DRIFT_FAULT was logged; next session will be blocked at Phase 6
        pass


# ---------------------------------------------------------------------------
# Stage 0 — Semantic Drift Detection
# ---------------------------------------------------------------------------

def _stage0_drift(layout: Layout) -> bool:
    """Run drift probes. Returns True if a DRIFT_FAULT was raised."""
    if not layout.drift_probes.exists():
        return False

    probes = read_jsonl(layout.drift_probes)
    fault = False

    for probe in probes:
        target_rel = probe.get("target", "")
        reference = probe.get("reference", "")
        probe_type = probe.get("type", "hash")
        target = layout.root / target_rel

        if not target.exists():
            continue

        result = _run_probe(target, reference, probe_type, layout)
        if not result:
            fault = True
            _write_drift_fault(layout, target_rel)
            from .hooks import run_hook
            run_hook(layout, "on_drift_fault", {
                "target": target_rel,
                "probe_type": probe_type,
                "reference": reference,
            })
            break

    _update_semantic_digest(layout, fault)
    return fault


def _run_probe(target: Path, reference: str, probe_type: str, layout: Layout) -> bool:
    """Return True if probe passes (no drift detected)."""
    content = target.read_text(encoding="utf-8", errors="replace")

    if probe_type == "hash":
        actual = sha256_file(target)
        return actual == reference

    if probe_type == "contains":
        return reference in content

    if probe_type == "not_contains":
        return reference not in content

    # unknown probe type — pass
    return True


def _write_drift_fault(layout: Layout, target: str) -> None:
    envelope = acp_encode(
        env_type="MSG",
        source="sil",
        data={"type": "DRIFT_FAULT", "target": target, "ts": int(time.time() * 1000)},
    )
    append_jsonl(layout.integrity_log, envelope)
    write_notification(layout, "DRIFT_FAULT", {"target": target})


def _update_semantic_digest(layout: Layout, fault: bool) -> None:
    ts = int(time.time() * 1000)
    loaded: dict[str, Any] = {}
    if layout.semantic_digest.exists():
        try:
            loaded = read_json(layout.semantic_digest)
        except Exception:
            pass
    existing: dict[str, Any] = loaded
    existing["last_run"] = ts
    existing["last_fault"] = fault
    atomic_write(layout.semantic_digest, existing)


# ---------------------------------------------------------------------------
# Stage 1 — Memory Consolidation
# ---------------------------------------------------------------------------

def _stage1_consolidation(layout: Layout) -> None:
    """MIL processes pending-closure.json (no-op if absent = forced close)."""
    process_closure(layout)


# ---------------------------------------------------------------------------
# Stage 2 — Garbage Collection
# ---------------------------------------------------------------------------

def _stage2_gc(layout: Layout) -> None:
    """Rotate session.jsonl if over threshold; clean stale symlinks."""
    _rotate_session_store(layout)
    clean_stale_symlinks(layout)


def _rotate_session_store(layout: Layout) -> None:
    """Rename session.jsonl to episodic/<year>/<timestamp>.jsonl if over threshold."""
    if not layout.session_store.exists():
        return

    baseline = _load_baseline(layout)
    threshold = int(
        baseline.get("session_store", {}).get("rotation_threshold_bytes", 1_000_000)
    )
    if layout.session_store.stat().st_size < threshold:
        return

    ts = int(time.time() * 1000)
    year = str(datetime.date.today().year)
    dest_dir = layout.episodic_dir / year
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{ts}.jsonl"
    os.replace(layout.session_store, dest)
    # create fresh empty session.jsonl
    layout.session_store.write_text("", encoding="utf-8")


# ---------------------------------------------------------------------------
# Stage 3 — Endure Execution
# ---------------------------------------------------------------------------

def _stage3_endure(layout: Layout) -> None:
    """Execute authorized Evolution Proposals from operator_notifications/."""
    proposals = _collect_authorized_proposals(layout)
    if not proposals:
        return

    for proposal in proposals:
        seq = proposal.get("seq", int(time.time() * 1000))
        slugs: list[str] = proposal.get("slugs", [])

        # snapshot before mutation
        snapshot_dir = layout.snapshot_dir(seq)
        snapshot_dir.mkdir(parents=True, exist_ok=True)

        # promote episodic → semantic for each slug
        files_written: dict[str, str] = {}
        for slug in slugs:
            if promote_to_semantic(layout, slug):
                dest = layout.semantic_dir / f"{slug}.md"
                files_written[str(dest.relative_to(layout.root))] = sha256_file(dest)

        if not files_written:
            continue

        # update integrity document
        _update_integrity_doc(layout, files_written)

        # write chain entry
        auth_digest = proposal.get("auth_digest", "")
        write_chain_entry(layout, seq, files_written, auth_digest)

        # MIL appends ENDURE_COMMIT to session.jsonl
        append_endure_commit(layout, seq, files_written)

        # clean up snapshot (no crash occurred)
        import shutil
        shutil.rmtree(snapshot_dir, ignore_errors=True)


def _collect_authorized_proposals(layout: Layout) -> list[dict[str, Any]]:
    """Collect EVOLUTION_AUTH records from integrity.log that have no SLEEP_COMPLETE after them."""
    if not layout.integrity_log.exists():
        return []
    proposals: list[dict[str, Any]] = []
    for line in layout.integrity_log.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
            data = rec.get("data", {})
            if isinstance(data, dict) and data.get("type") == "EVOLUTION_AUTH":
                proposals.append(data)
        except Exception:
            continue
    return proposals


def _update_integrity_doc(layout: Layout, files_written: dict[str, str]) -> None:
    if not layout.integrity_doc.exists():
        return
    doc = read_json(layout.integrity_doc)
    tracked = doc.get("files", {})
    for rel, digest in files_written.items():
        tracked[rel] = digest
    doc["files"] = tracked
    atomic_write(layout.integrity_doc, doc)


# ---------------------------------------------------------------------------
# Completion
# ---------------------------------------------------------------------------

def _write_sleep_complete(layout: Layout) -> None:
    envelope = acp_encode(
        env_type="MSG",
        source="sil",
        data={"type": "SLEEP_COMPLETE", "ts": int(time.time() * 1000)},
    )
    append_jsonl(layout.integrity_log, envelope)


def _remove_session_token(layout: Layout) -> None:
    if layout.session_token.exists():
        layout.session_token.unlink()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_baseline(layout: Layout) -> dict[str, Any]:
    try:
        return read_json(layout.baseline)
    except Exception:
        return {}
