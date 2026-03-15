"""
Boot Sequence.  §5

Deterministic gated pipeline executed on every startup after FAP.
Each phase must pass before the next executes.  Any failure raises BootError
and no session token is issued.

Also handles cold-start detection and FAP delegation (§4).
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from .acp import ACPEnvelope, crc32
from .fap import FAPError, run as fap_run
from .formats import IntegrityDocument, ImprintRecord, SkillIndex, StructuralBaseline
from .sil import (
    _utcnow,
    activate_beacon,
    beacon_is_active,
    build_skill_index,
    issue_session_token,
    operator_channel_available,
    session_token_present,
    verify_integrity_chain,
    verify_structural_files,
)
from .store import Layout, append_jsonl, read_json, read_jsonl


class BootError(Exception):
    """Raised when any boot phase cannot pass.  No session token is issued."""


@dataclass
class BootResult:
    session_id: str
    is_first_boot: bool = False
    crash_recovered: bool = False
    pending_proposals: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run(layout: Layout) -> BootResult:
    """Execute the boot sequence.  Returns BootResult on success.

    Raises BootError if any phase fails.
    Raises FAPError (from fap.run) if this is a cold-start and FAP fails.
    """
    # Cold-start detection: absence of memory/imprint.json → run FAP.
    if not layout.imprint.exists():
        session_id = fap_run(layout)
        return BootResult(session_id=session_id, is_first_boot=True)

    # Prerequisite: Passive Distress Beacon check.
    if beacon_is_active(layout):
        raise BootError(
            "Passive Distress Beacon is active.  "
            "Resolve the underlying condition and clear the beacon before booting."
        )

    # ------------------------------------------------------------------
    # Phase 0 — Operator Bound Verification
    # ------------------------------------------------------------------
    try:
        imprint_data = read_json(layout.imprint)
        ImprintRecord.from_dict(imprint_data)
    except (FileNotFoundError, KeyError, TypeError, ValueError) as exc:
        raise BootError(f"Phase 0: Imprint Record invalid or missing: {exc}") from exc

    notif_ok, terminal_ok = operator_channel_available(layout)
    if not notif_ok:
        raise BootError("Phase 0: operator_notifications/ is not writable")
    if not terminal_ok:
        raise BootError("Phase 0: terminal prompt is not available")

    # ------------------------------------------------------------------
    # Phase 1 — Host Introspection
    # ------------------------------------------------------------------
    try:
        baseline = StructuralBaseline.from_dict(read_json(layout.baseline))
    except (FileNotFoundError, KeyError, TypeError, ValueError) as exc:
        raise BootError(f"Phase 1: state/baseline.json invalid: {exc}") from exc

    if baseline.cpe.topology != "transparent":
        raise BootError(
            f"Phase 1: CPE topology must be 'transparent', "
            f"got '{baseline.cpe.topology}'"
        )

    if baseline.watchdog_sil_threshold_seconds > baseline.heartbeat_interval_seconds:
        raise BootError(
            "Phase 1: watchdog.sil_threshold_seconds > heartbeat.interval_seconds "
            "— watchdog cannot detect SIL silence within a single Heartbeat window"
        )

    # ------------------------------------------------------------------
    # Phase 2 — Crash Recovery
    # ------------------------------------------------------------------
    crash_recovered = False
    if session_token_present(layout):
        crash_recovered = True
        _crash_recovery(layout, baseline)

    # ------------------------------------------------------------------
    # Phase 3 — Integrity Verification
    # ------------------------------------------------------------------
    try:
        integrity_doc = IntegrityDocument.from_dict(read_json(layout.integrity_doc))
    except (FileNotFoundError, KeyError, TypeError, ValueError) as exc:
        raise BootError(f"Phase 3: state/integrity.json invalid: {exc}") from exc

    if not verify_integrity_chain(layout, integrity_doc):
        raise BootError("Phase 3: Integrity Chain verification failed")

    mismatches = verify_structural_files(layout, integrity_doc)
    if mismatches:
        raise BootError(
            f"Phase 3: structural file hash mismatch(es): {', '.join(mismatches)}"
        )

    # ------------------------------------------------------------------
    # Phase 4 — Skill Index Resolution
    # ------------------------------------------------------------------
    try:
        SkillIndex.from_dict(read_json(layout.skills_index))
    except (FileNotFoundError, KeyError, TypeError, ValueError) as exc:
        raise BootError(f"Phase 4: skills/index.json invalid: {exc}") from exc

    # Phase 5 — Context Assembly is handled by session.py (not a boot gate).

    # ------------------------------------------------------------------
    # Phase 6 — Critical Condition Check
    # ------------------------------------------------------------------
    pending_proposals = _check_critical_conditions(layout)

    # ------------------------------------------------------------------
    # Phase 7 — Session Token Issuance
    # ------------------------------------------------------------------
    session_id = issue_session_token(layout)

    # Phase 7 — on_boot hook
    from .hooks import run_hook
    run_hook(layout, "on_boot", {"session_id": session_id})

    return BootResult(
        session_id=session_id,
        crash_recovered=crash_recovered,
        pending_proposals=pending_proposals,
    )


# ---------------------------------------------------------------------------
# Phase 2 — Crash Recovery detail  (§5.2)
# ---------------------------------------------------------------------------

def _crash_recovery(layout: Layout, baseline: StructuralBaseline) -> None:
    """Handle stale session token found at boot.  §5.2"""
    from .hooks import run_hook
    run_hook(layout, "on_crash_recovery", {
        "crash_count": _read_crash_count(read_jsonl(layout.integrity_log)),
        "max_consecutive": baseline.fault_n_boot,
    })

    # Step 0: ensure session.jsonl exists (rotation may have removed it).
    if not layout.session_store.exists():
        layout.session_store.write_text("", encoding="utf-8")

    # Step 1: restore partial Endure snapshot if present.
    _restore_partial_endure(layout)

    # Step 2: present unresolved ACTION_LEDGER entries to Operator.
    _resolve_action_ledger(layout)

    # Step 3: re-run Sleep Cycle to consolidate the crashed session.
    try:
        from . import sleep as sleep_mod
        sleep_mod.run_sleep_cycle(layout)
    except ImportError:
        pass  # sleep.py not yet implemented — acceptable during development
    except Exception as exc:
        # Sleep Cycle failed — increment counter before raising
        crash_count = _increment_crash_counter(layout)
        if crash_count >= baseline.fault_n_boot:
            activate_beacon(layout, "n_boot", crash_count)
            raise BootError(
                f"Phase 2: {crash_count} consecutive boot failures — "
                f"Passive Distress Beacon activated. "
                f"Last Sleep Cycle error: {exc}"
            ) from exc
        raise BootError(
            f"Phase 2: Sleep Cycle failed during crash recovery "
            f"(attempt {crash_count}/{baseline.fault_n_boot}): {exc}"
        ) from exc

    # Step 4: Sleep Cycle completed — remove stale session token and reset counter.
    if layout.session_token.exists():
        layout.session_token.unlink()
    _reset_crash_counter(layout)


def _restore_partial_endure(layout: Layout) -> None:
    """Restore pre-mutation snapshot for any partial ENDURE_COMMIT.  §5.2 step 2."""
    import shutil

    log_entries = read_jsonl(layout.integrity_log)

    # Find the last ENDURE_COMMIT and last SLEEP_COMPLETE seqs.
    last_endure_seq: int | None = None
    last_sleep_seq: int | None = None
    for entry in log_entries:
        t = entry.get("type", "")
        data_str = entry.get("data", "{}")
        try:
            data = json.loads(data_str)
        except (json.JSONDecodeError, TypeError):
            data = {}
        seq = data.get("seq")
        if t == "ENDURE_COMMIT" and seq is not None:
            last_endure_seq = int(seq)
        elif t == "SLEEP_COMPLETE":
            last_sleep_seq_val = data.get("seq")
            if last_sleep_seq_val is not None:
                last_sleep_seq = int(last_sleep_seq_val)

    if last_endure_seq is None:
        return  # no Endure commit ever happened

    # Partial commit: ENDURE_COMMIT exists with no subsequent SLEEP_COMPLETE.
    endure_int: int = last_endure_seq  # not None — checked above
    is_partial = last_sleep_seq is None or endure_int > _int_or_zero(last_sleep_seq)
    if is_partial:
        snapshot_dir = layout.snapshot_dir(last_endure_seq)
        if snapshot_dir.is_dir():
            for src in snapshot_dir.iterdir():
                rel = src.name
                dst = layout.root / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
            shutil.rmtree(snapshot_dir)


def _resolve_action_ledger(layout: Layout) -> None:
    """Present unresolved ACTION_LEDGER entries to the Operator.  §5.2 step 3."""
    entries = read_jsonl(layout.session_store)
    unresolved: list[dict] = []
    resolved_ids: set[str] = set()

    for entry in entries:
        t = entry.get("type", "")
        try:
            data = json.loads(entry.get("data", "{}"))
        except (json.JSONDecodeError, TypeError):
            data = {}

        if t == "ACTION_LEDGER":
            ledger_id = data.get("id")
            status = data.get("status")
            if ledger_id and status == "in_progress":
                unresolved.append(data)
        elif t in ("SKILL_RESULT", "SKILL_ERROR", "SKILL_TIMEOUT"):
            ledger_id = data.get("ledger_id")
            if ledger_id:
                resolved_ids.add(ledger_id)

    pending = [e for e in unresolved if e.get("id") not in resolved_ids]
    if not pending:
        return

    print("\n=== Crash Recovery: Unresolved Actions ===")
    print("The following skills were in-progress when the session crashed:\n")
    for item in pending:
        print(f"  skill: {item.get('skill')}  id: {item.get('id')}")
    print()
    print("These will NOT be re-executed automatically.")
    print("Please investigate and re-run manually if needed.")
    input("Press Enter to continue boot...")


def _int_or_zero(v: int | None) -> int:
    return v if v is not None else 0


def _read_crash_count(entries: list[dict]) -> int:
    """Scan integrity.log entries (newest-first) and return the last crash count."""
    for entry in list(reversed(entries)):
        t = entry.get("type", "")
        if t == "SLEEP_COMPLETE":
            return 0
        try:
            data = json.loads(entry.get("data", "{}"))
        except (json.JSONDecodeError, TypeError):
            data = {}
        cc = data.get("crash_count")
        if t == "HEARTBEAT" and cc is not None:
            return int(cc)
    return 0


def _reset_crash_counter(layout: Layout) -> None:
    """Write a crash_count=0 HEARTBEAT entry to signal clean recovery."""
    ts = _utcnow()
    data_str = json.dumps({"crash_count": 0, "ts": ts})
    env = ACPEnvelope(
        actor="sil", gseq=0, tx=str(uuid.uuid4()),
        seq=1, eof=True, type="HEARTBEAT", ts=ts,
        data=data_str, crc=crc32(data_str),
    )
    append_jsonl(layout.integrity_log, env.to_dict())


def _increment_crash_counter(layout: Layout) -> int:
    """Increment the crash counter in integrity.log and return the new count."""
    entries = read_jsonl(layout.integrity_log)
    count: int = _read_crash_count(entries) + 1

    ts = _utcnow()
    data_str = json.dumps({"crash_count": count, "ts": ts})
    env = ACPEnvelope(
        actor="sil", gseq=0, tx=str(uuid.uuid4()),
        seq=1, eof=True, type="HEARTBEAT", ts=ts,
        data=data_str, crc=crc32(data_str),
    )
    append_jsonl(layout.integrity_log, env.to_dict())

    return count


# ---------------------------------------------------------------------------
# Phase 6 — Critical Condition Check  (§5, §10.8)
# ---------------------------------------------------------------------------

def _check_critical_conditions(layout: Layout) -> list[dict]:
    """Scan integrity.log for unresolved Critical conditions.

    Attempts automatic resolution for DRIFT_FAULT and SIL_UNRESPONSIVE.
    Presents SEVERANCE_PENDING to the Operator for manual resolution.
    Raises BootError if any condition remains unresolved after resolution attempts.
    Returns list of pending Evolution Proposals.
    """
    from .sil import log_cleared, sha256_file
    from .exec_ import _last_heartbeat_ts, _sil_threshold

    entries = read_jsonl(layout.integrity_log)

    critical_seqs: dict[int, str] = {}   # seq → type
    critical_data: dict[int, dict] = {}  # seq → parsed data
    cleared_seqs: set[int] = set()
    pending_proposals: list[dict] = []

    for i, entry in enumerate(entries):
        t = entry.get("type", "")
        seq = i + 1

        if t in ("DRIFT_FAULT", "IDENTITY_DRIFT", "SEVERANCE_PENDING", "SIL_UNRESPONSIVE"):
            critical_seqs[seq] = t
            try:
                critical_data[seq] = json.loads(entry.get("data", "{}"))
            except Exception:
                critical_data[seq] = {}

        elif t == "CRITICAL_CLEARED":
            try:
                data = json.loads(entry.get("data", "{}"))
                clears = int(data.get("clears_seq", -1))
                cleared_seqs.add(clears)
            except (json.JSONDecodeError, TypeError, ValueError):
                pass

        elif t == "PROPOSAL_PENDING":
            try:
                data = json.loads(entry.get("data", "{}"))
                pending_proposals.append({"seq": seq, **data})
            except (json.JSONDecodeError, TypeError):
                pass

    unresolved = {s: t for s, t in critical_seqs.items() if s not in cleared_seqs}

    still_unresolved: dict[int, str] = {}

    for seq, ctype in unresolved.items():
        data = critical_data.get(seq, {})

        if ctype == "DRIFT_FAULT":
            if _try_resolve_drift_fault(layout, seq, data, sha256_file, log_cleared):
                continue

        elif ctype == "SIL_UNRESPONSIVE":
            if _try_resolve_sil_unresponsive(layout, seq, _last_heartbeat_ts, _sil_threshold, log_cleared):
                continue

        elif ctype == "SEVERANCE_PENDING":
            if _try_resolve_severance(layout, seq, data, log_cleared):
                continue

        still_unresolved[seq] = ctype

    if still_unresolved:
        descriptions = [f"seq={s} type={t}" for s, t in still_unresolved.items()]
        raise BootError(
            f"Phase 6: unresolved Critical condition(s): {'; '.join(descriptions)}"
        )

    return pending_proposals


def _try_resolve_drift_fault(
    layout: Layout, seq: int, data: dict, sha256_file, log_cleared
) -> bool:
    """Re-run the drift probe for the faulted target. Clear if it passes now."""
    target_rel = data.get("target", "")
    if not target_rel:
        return False
    target = layout.root / target_rel
    if not target.exists():
        return False

    # Load probe reference from drift-probes.jsonl
    probes = read_jsonl(layout.drift_probes) if layout.drift_probes.exists() else []
    probe = next((p for p in probes if p.get("target") == target_rel), None)
    if probe is None:
        return False

    reference = probe.get("reference", "")
    probe_type = probe.get("type", "hash")

    passed = False
    if probe_type == "hash":
        passed = sha256_file(target) == reference
    elif probe_type == "contains":
        passed = reference in target.read_text(encoding="utf-8", errors="replace")
    elif probe_type == "not_contains":
        passed = reference not in target.read_text(encoding="utf-8", errors="replace")

    if passed:
        log_cleared(layout, seq)
        print(f"  [Phase 6] DRIFT_FAULT seq={seq} resolved: probe passes.")
        return True

    print(f"  [Phase 6] DRIFT_FAULT seq={seq} still active: probe fails for '{target_rel}'.")
    return False


def _try_resolve_sil_unresponsive(
    layout: Layout, seq: int, last_heartbeat_ts_fn, sil_threshold_fn, log_cleared
) -> bool:
    """Clear SIL_UNRESPONSIVE if SIL heartbeat is now within threshold."""
    threshold = sil_threshold_fn(layout)
    last_hb = last_heartbeat_ts_fn(layout)
    if last_hb is None:
        return False
    import time
    elapsed = time.time() - last_hb
    if elapsed <= threshold:
        log_cleared(layout, seq)
        print(f"  [Phase 6] SIL_UNRESPONSIVE seq={seq} resolved: heartbeat within threshold.")
        return True
    print(f"  [Phase 6] SIL_UNRESPONSIVE seq={seq} still active: elapsed={elapsed:.0f}s > threshold={threshold}s.")
    return False


def _try_resolve_severance(
    layout: Layout, seq: int, data: dict, log_cleared
) -> bool:
    """Present SEVERANCE_PENDING to Operator. On approve → clear. On reject → re-audit hash."""
    skill_name = data.get("skill", "<unknown>")
    issues = data.get("issues", [])

    print(f"\n[SEVERANCE PENDING] Skill '{skill_name}' was removed mid-session.")
    if issues:
        print("  Issues detected:")
        for issue in issues:
            print(f"    - {issue}")
    print("  Options: approve (keep removed) | reject (re-audit and restore if clean)")
    try:
        answer = input("  Decision [approve/reject]: ").strip().lower()
    except EOFError:
        answer = "approve"

    if answer == "approve":
        log_cleared(layout, seq)
        print(f"  Severance approved. Skill '{skill_name}' remains removed.")
        return True

    # reject: re-audit hash
    if not layout.integrity_doc.exists() or not layout.skills_index.exists():
        print(f"  Cannot re-audit: integrity doc or skill index missing.")
        return False

    try:
        doc = read_json(layout.integrity_doc)
        tracked: dict = doc.get("files", {})
        index = read_json(layout.skills_index)
    except Exception:
        return False

    # Find the skill's exe path from tracked files or manifest
    from .store import atomic_write
    skills: list[dict] = index.get("skills", [])
    # Try to find in a disabled/backup list or by scanning manifests
    skill_entry = _find_skill_manifest(layout, skill_name)
    if skill_entry is None:
        print(f"  Cannot locate manifest for '{skill_name}' — severance maintained.")
        return False

    exe_rel = skill_entry.get("exe", "")
    exe_path = layout.root / exe_rel if exe_rel else None
    if not exe_path or not exe_path.is_file():
        print(f"  Skill executable not found — severance maintained.")
        return False

    expected = tracked.get(exe_rel)
    if expected is None:
        print(f"  Skill not tracked in Integrity Document — severance maintained.")
        return False

    from .sil import sha256_file as _sha
    actual = _sha(exe_path)
    if actual == expected:
        # Restore to index
        skills.append(skill_entry)
        index["skills"] = skills
        atomic_write(layout.skills_index, index)
        log_cleared(layout, seq)
        print(f"  Re-audit passed. Skill '{skill_name}' restored to index.")
        return True

    print(f"  Re-audit failed: hash mismatch. Severance maintained.")
    return False


def _find_skill_manifest(layout: Layout, skill_name: str) -> dict | None:
    """Locate a skill entry by scanning manifest files under skills/."""
    for mdir in [layout.skills_lib_dir, layout.skills_dir]:
        if not mdir.exists():
            continue
        candidate = mdir / skill_name / "manifest.json"
        if candidate.exists():
            try:
                m = read_json(candidate)
                if m.get("name") == skill_name or mdir == layout.skills_lib_dir:
                    # Build a minimal index entry
                    exe = m.get("exe", f"skills/lib/{skill_name}/run.py" if mdir == layout.skills_lib_dir else f"skills/{skill_name}/run.py")
                    return {
                        "name": skill_name,
                        "exe": exe,
                        "class": m.get("class", "builtin"),
                        "manifest": str(candidate.relative_to(layout.root)),
                    }
            except Exception:
                pass
    return None
