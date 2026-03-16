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
import shutil
import time
import uuid
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
    sha256_str,
    verify_structural_files,
    write_chain_entry,
    last_chain_seq,
    write_notification,
    log_critical,
)
from .formats import ChainEntry, ChainEntryType
from .store import Layout, append_jsonl, atomic_write, load_baseline, read_json, read_jsonl


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

    # Convert any unresolved SEVERANCE_COMMIT entries to SEVERANCE_PENDING
    _promote_severance_pending(layout)

    # Write SLEEP_COMPLETE
    _write_sleep_complete(layout)

    # Remove session token (last act)
    _remove_session_token(layout)


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
# Severance promotion — SEVERANCE_COMMIT → SEVERANCE_PENDING
# ---------------------------------------------------------------------------

def _promote_severance_pending(layout: Layout) -> None:
    """At end of Sleep Cycle, promote any unresolved SEVERANCE_COMMIT to SEVERANCE_PENDING.

    A SEVERANCE_COMMIT is considered unresolved if no subsequent CRITICAL_CLEARED
    references its log position. Each unresolved commit becomes a SEVERANCE_PENDING
    that will block the next boot until the Operator resolves it via /endure.
    """
    entries = read_jsonl(layout.integrity_log)
    cleared_seqs: set[int] = set()

    for i, entry in enumerate(entries):
        raw_data = entry.get("data", "{}")
        try:
            data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
        except Exception:
            continue
        if isinstance(data, dict) and data.get("type") == "CRITICAL_CLEARED":
            try:
                cleared_seqs.add(int(data.get("clears_seq", -1)))
            except Exception:
                pass

    for i, entry in enumerate(entries):
        raw_data = entry.get("data", "{}")
        try:
            data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
        except Exception:
            continue
        if isinstance(data, dict) and data.get("type") == "SEVERANCE_COMMIT":
            seq = i + 1  # 1-indexed
            if seq not in cleared_seqs:
                log_critical(layout, "SEVERANCE_PENDING", data)
                write_notification(layout, "critical", {
                    "type": "SEVERANCE_PENDING",
                    "detail": data,
                })


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

    baseline = load_baseline(layout)
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
    """Execute authorized Evolution Proposals from integrity.log."""
    proposals = _collect_authorized_proposals(layout)
    if not proposals:
        return

    for proposal in proposals:
        seq = int(time.time() * 1000)
        auth_digest = proposal.get("auth_digest", "")
        content = proposal.get("content", {})
        if isinstance(content, str):
            try:
                content = json.loads(content)
            except Exception:
                content = {}

        # snapshot before mutation
        snapshot_dir = layout.snapshot_dir(seq)
        snapshot_dir.mkdir(parents=True, exist_ok=True)

        files_written: dict[str, str] = {}

        # apply structural changes
        changes: list[dict[str, Any]] = content.get("changes", []) if isinstance(content, dict) else []
        for change in changes:
            op = change.get("op", "")
            if not op:
                continue

            # skill_install: moves workspace/stage/<name>/ → skills/<name>/
            # path is determined by FCP, not by the proposal
            if op == "skill_install":
                skill_name = change.get("name", "").strip()
                if not skill_name:
                    continue
                source = (layout.root / "workspace" / "stage" / skill_name).resolve()
                dest = (layout.root / "skills" / skill_name).resolve()
                stage_manifest = source / "manifest.json"
                if not stage_manifest.exists():
                    continue
                try:
                    m = json.loads(stage_manifest.read_text(encoding="utf-8"))
                    if m.get("class") == "builtin":
                        continue
                    if dest.exists():
                        shutil.rmtree(dest)
                    shutil.copytree(source, dest)
                    shutil.rmtree(source)
                    for f in dest.rglob("*"):
                        if f.is_file():
                            files_written[str(f.relative_to(layout.root))] = sha256_file(f)
                    # add to skills/index.json
                    _index_skill(layout, skill_name, m)
                except Exception:
                    continue
                continue

            # cron_add: registers a scheduled task in state/agenda.json
            if op == "cron_add":
                required = ("description", "executor", "task", "schedule")
                if not all(change.get(f) for f in required):
                    continue
                executor = change.get("executor", "")
                if executor not in ("worker", "cpe"):
                    continue
                task_val = change.get("task", "")
                tools_val = change.get("tools", "")
                from .operator import _build_wake_up_message
                wake_up_message = _build_wake_up_message(task_val, executor, tools_val)
                task_entry: dict[str, Any] = {
                    "id": f"cron_{uuid.uuid4().hex[:12]}",
                    "status": "pending",
                    "executor": executor,
                    "description": change.get("description", ""),
                    "tools": tools_val,
                    "task": task_val,
                    "schedule": change.get("schedule", ""),
                    "wake_up_message": wake_up_message,
                    "proposed_at": datetime.datetime.utcnow().isoformat() + "Z",
                    "approved_at": None,
                    "last_run": None,
                }
                agenda_path = layout.agenda
                agenda: dict[str, Any] = {"tasks": []}
                if agenda_path.exists():
                    try:
                        agenda = json.loads(agenda_path.read_text(encoding="utf-8"))
                    except Exception:
                        pass
                agenda.setdefault("tasks", []).append(task_entry)
                agenda_path.parent.mkdir(parents=True, exist_ok=True)
                agenda_path.write_text(json.dumps(agenda, indent=2), encoding="utf-8")
                files_written[str(agenda_path.relative_to(layout.root))] = sha256_file(agenda_path)
                write_notification(layout, "cron_proposed", {
                    "id": task_entry["id"],
                    "description": task_entry["description"],
                })
                continue

            target_rel = change.get("target", "")
            if not target_rel:
                continue
            target = (layout.root / target_rel).resolve()
            # security: must stay within entity root, never in workspace/
            try:
                target.relative_to(layout.root)
            except ValueError:
                continue
            if str(target).startswith(str((layout.root / "workspace").resolve())):
                continue
            # security: file ops cannot touch skills/ — use skill_install op instead
            if str(target).startswith(str((layout.root / "skills").resolve())):
                continue

            try:
                if op == "json_merge":
                    patch = change.get("patch", {})
                    existing: dict[str, Any] = {}
                    if target.exists():
                        existing = json.loads(target.read_text(encoding="utf-8"))
                    _deep_merge(existing, patch)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(json.dumps(existing, indent=2), encoding="utf-8")
                    files_written[str(target.relative_to(layout.root))] = sha256_file(target)

                elif op == "file_write":
                    file_content = change.get("content", "")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(file_content, encoding="utf-8")
                    files_written[str(target.relative_to(layout.root))] = sha256_file(target)

                elif op == "file_delete":
                    if target.exists():
                        target.unlink()
                        files_written[str(target.relative_to(layout.root))] = "deleted"
            except Exception:
                continue

        # promote episodic → semantic for legacy slug-based proposals
        slugs: list[str] = proposal.get("slugs", [])
        for slug in slugs:
            if promote_to_semantic(layout, slug):
                dest = layout.semantic_dir / f"{slug}.md"
                files_written[str(dest.relative_to(layout.root))] = sha256_file(dest)

        if not files_written:
            shutil.rmtree(snapshot_dir, ignore_errors=True)
            continue

        # update integrity document
        _update_integrity_doc(layout, files_written)

        # write chain entry
        prev_seq = last_chain_seq(layout)
        prev_hash: str | None = None
        if layout.integrity_chain.exists():
            lines = [l.strip() for l in layout.integrity_chain.read_text(encoding="utf-8").splitlines() if l.strip()]
            if lines:
                prev_hash = sha256_str(lines[-1])
        integrity_doc_hash = sha256_file(layout.integrity_doc) if layout.integrity_doc.exists() else None
        entry = ChainEntry(
            seq=prev_seq + 1,
            type=ChainEntryType.ENDURE_COMMIT,
            ts=str(time.time()),
            prev_hash=prev_hash,
            evolution_auth_digest=auth_digest,
            files=files_written,
            integrity_doc_hash=integrity_doc_hash,
        )
        write_chain_entry(layout, entry)

        # MIL appends ENDURE_COMMIT to session.jsonl
        append_endure_commit(layout, seq, files_written)

        # clean up snapshot (no crash occurred)
        shutil.rmtree(snapshot_dir, ignore_errors=True)


def _index_skill(layout: Layout, skill_name: str, manifest: dict[str, Any]) -> None:
    """Add or update a skill entry in skills/index.json after skill_install."""
    index_path = layout.skills_index
    if not index_path.exists():
        return
    try:
        idx = json.loads(index_path.read_text(encoding="utf-8"))
    except Exception:
        return
    skills: list[dict[str, Any]] = idx.get("skills", [])
    # remove existing entry with same name if present
    skills = [s for s in skills if s.get("name") != skill_name]
    skills.append({
        "name": skill_name,
        "desc": manifest.get("description", ""),
        "manifest": f"skills/{skill_name}/manifest.json",
        "class": manifest.get("class", "custom"),
    })
    idx["skills"] = skills
    atomic_write(index_path, idx)


def _deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> None:
    """Recursively merge patch into base in-place. Lists are replaced, not extended."""
    for key, val in patch.items():
        if isinstance(val, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], val)
        else:
            base[key] = val


def _collect_authorized_proposals(layout: Layout) -> list[dict[str, Any]]:
    """Collect EVOLUTION_AUTH records from integrity.log that have no SLEEP_COMPLETE after them.

    Only proposals that appear after the last SLEEP_COMPLETE are pending execution.
    """
    if not layout.integrity_log.exists():
        return []

    # Find the index of the last SLEEP_COMPLETE — only proposals after it are pending.
    lines = [l.strip() for l in layout.integrity_log.read_text(encoding="utf-8").splitlines() if l.strip()]
    last_sleep_idx = -1
    for i, line in enumerate(lines):
        try:
            rec = json.loads(line)
            raw_data = rec.get("data", "{}")
            data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
            if isinstance(data, dict) and data.get("type") == "SLEEP_COMPLETE":
                last_sleep_idx = i
        except Exception:
            continue

    proposals: list[dict[str, Any]] = []
    for line in lines[last_sleep_idx + 1:]:
        try:
            rec = json.loads(line)
            raw_data = rec.get("data", "{}")
            data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
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

