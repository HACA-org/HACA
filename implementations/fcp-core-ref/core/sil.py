"""System Integrity Layer (SIL) — FCP-Core §10 MVP subset.

MVP scope (Fase 1):
  - SHA-256 hash computation and Integrity Document build/verify (§10.1)
  - Integrity Chain validation — root entry present check (§10.1)
  - Session token lifecycle: issue / revoke / remove (§3.5)
  - Integrity Log append (state/integrity.log) (§10)
  - HEARTBEAT envelope write (§10.3, simplified — no background thread)
  - Distress Beacon check and activation (§10.7)
  - Crash counter tracking in integrity.log

Deferred to Fase 2:
  - Background Heartbeat threading loop
  - Reciprocal SIL Watchdog
  - Full drift detection (NCD/gzip)
  - Evolution Gate / Endure execution
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path
from typing import Any

from .acp import (
    ACPEnvelope,
    GseqCounter,
    TYPE_HEARTBEAT,
    TYPE_SLEEP_COMPLETE,
    ACTOR_SIL,
    build_envelope,
)
from .fs import (
    atomic_write_json,
    append_jsonl,
    read_json,
    read_jsonl,
    utcnow_iso,
)


# ---------------------------------------------------------------------------
# Tracked structural files (§3.3)
# ---------------------------------------------------------------------------
#
# FCP-Core §3.3: tracked files are:
#   boot.md, all files in persona/, skills/index.json,
#   all skill manifest.json files, all files in hooks/, state/baseline.json
#
# The SIL discovers these dynamically from the entity root at runtime.

def _tracked_files(entity_root: Path) -> list[Path]:
    """Return all structural files that must appear in the Integrity Document."""
    files: list[Path] = []

    # boot.md
    boot_md = entity_root / "boot.md"
    if boot_md.exists():
        files.append(boot_md)

    # persona/ — all files recursively
    persona_dir = entity_root / "persona"
    if persona_dir.exists():
        for p in sorted(persona_dir.rglob("*")):
            if p.is_file():
                files.append(p)

    # skills/index.json
    skill_index = entity_root / "skills" / "index.json"
    if skill_index.exists():
        files.append(skill_index)

    # skills/<name>/manifest.json
    skills_dir = entity_root / "skills"
    if skills_dir.exists():
        for manifest in sorted(skills_dir.glob("*/manifest.json")):
            files.append(manifest)

    # hooks/ — all files
    hooks_dir = entity_root / "hooks"
    if hooks_dir.exists():
        for p in sorted(hooks_dir.rglob("*")):
            if p.is_file():
                files.append(p)

    # state/baseline.json
    baseline = entity_root / "state" / "baseline.json"
    if baseline.exists():
        files.append(baseline)

    return files


# ---------------------------------------------------------------------------
# Hash utilities
# ---------------------------------------------------------------------------

def compute_file_hash(path: str | Path) -> str:
    """Return the SHA-256 hex digest of the file at *path*."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def compute_bytes_hash(data: bytes) -> str:
    """Return the SHA-256 hex digest of *data*."""
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Integrity Document (§3.3)
# ---------------------------------------------------------------------------

def build_integrity_document(entity_root: str | Path) -> dict[str, Any]:
    """Compute SHA-256 hashes for all tracked structural files.

    Returns the Integrity Document dict (not yet written to disk).
    """
    entity_root = Path(entity_root)
    files: dict[str, str] = {}
    for f in _tracked_files(entity_root):
        rel = str(f.relative_to(entity_root))
        files[rel] = compute_file_hash(f)

    return {
        "version": "1.0",
        "algorithm": "sha256",
        "files": files,
    }


def write_integrity_document(entity_root: str | Path, doc: dict[str, Any]) -> None:
    """Write the Integrity Document atomically to ``state/integrity.json``."""
    atomic_write_json(Path(entity_root) / "state" / "integrity.json", doc)


def verify_integrity_document(entity_root: str | Path) -> tuple[bool, list[str]]:
    """Recompute hashes and compare against ``state/integrity.json``.

    Returns:
        (ok, errors) — ok is True iff all hashes match and no unexpected
        files are present.  errors contains descriptions of any mismatches.
    """
    entity_root = Path(entity_root)
    doc_path = entity_root / "state" / "integrity.json"
    if not doc_path.exists():
        return False, ["integrity.json not found"]

    doc = read_json(doc_path)
    expected: dict[str, str] = doc.get("files", {})
    errors: list[str] = []

    tracked = _tracked_files(entity_root)
    tracked_rels = {str(f.relative_to(entity_root)) for f in tracked}

    # Check every tracked file that exists
    for f in tracked:
        rel = str(f.relative_to(entity_root))
        actual_hash = compute_file_hash(f)
        if rel not in expected:
            errors.append(f"unauthorized addition: {rel} not in Integrity Document")
        elif expected[rel] != actual_hash:
            errors.append(f"hash mismatch: {rel}")

    # Check for files in document that are now missing
    for rel, _h in expected.items():
        if rel not in tracked_rels:
            fp = entity_root / rel
            if not fp.exists():
                errors.append(f"missing tracked file: {rel}")

    return len(errors) == 0, errors


# ---------------------------------------------------------------------------
# Integrity Chain (§10.1, §7.4)
# ---------------------------------------------------------------------------

def verify_integrity_chain(entity_root: str | Path) -> tuple[bool, str]:
    """Validate that the Integrity Chain has at least a valid root entry.

    MVP-level check: verifies the root (Genesis Omega) entry exists and
    has the required fields.  Full chain traversal is Fase 2.

    Returns:
        (ok, error_message) — ok is True iff validation passes.
    """
    entity_root = Path(entity_root)
    chain_path = entity_root / "state" / "integrity_chain.jsonl"
    if not chain_path.exists():
        return False, "integrity_chain.jsonl not found"

    entries = read_jsonl(chain_path)
    if not entries:
        return False, "integrity_chain.jsonl is empty — Genesis Omega absent"

    root = entries[0]
    required = {"type", "genesis_omega", "ts", "entity_id"}
    missing = required - set(root.keys())
    if missing:
        return False, f"root chain entry missing fields: {missing}"

    if root.get("type") != "GENESIS_OMEGA":
        return False, f"first chain entry type must be GENESIS_OMEGA, got {root.get('type')!r}"

    return True, ""


def append_chain_entry(entity_root: str | Path, entry: dict[str, Any]) -> None:
    """Append an entry to ``state/integrity_chain.jsonl``."""
    append_jsonl(Path(entity_root) / "state" / "integrity_chain.jsonl", entry)


# ---------------------------------------------------------------------------
# Session Token (§3.5)
# ---------------------------------------------------------------------------

def issue_session_token(entity_root: str | Path) -> str:
    """Write a new session token and return the session_id.

    Creates ``state/sentinels/session.token`` atomically.
    """
    entity_root = Path(entity_root)
    token_path = entity_root / "state" / "sentinels" / "session.token"
    token_path.parent.mkdir(parents=True, exist_ok=True)

    session_id = str(uuid.uuid4())
    token = {
        "session_id": session_id,
        "issued_at": utcnow_iso(),
    }
    atomic_write_json(token_path, token)
    return session_id


def revoke_session_token(entity_root: str | Path) -> None:
    """Revoke the active session token by adding ``revoked_at``.

    The artefact remains in place (crash indicator) until removed after
    Sleep Cycle completion (see remove_session_token).
    """
    entity_root = Path(entity_root)
    token_path = entity_root / "state" / "sentinels" / "session.token"
    if not token_path.exists():
        return
    token = read_json(token_path)
    token["revoked_at"] = utcnow_iso()
    atomic_write_json(token_path, token)


def remove_session_token(entity_root: str | Path) -> None:
    """Remove the session token artefact after Sleep Cycle completes."""
    token_path = Path(entity_root) / "state" / "sentinels" / "session.token"
    token_path.unlink(missing_ok=True)


def read_session_token(entity_root: str | Path) -> dict[str, Any] | None:
    """Read and return the session token, or None if absent."""
    token_path = Path(entity_root) / "state" / "sentinels" / "session.token"
    if not token_path.exists():
        return None
    try:
        return read_json(token_path)
    except Exception:
        return None


def is_session_active(entity_root: str | Path) -> bool:
    """Return True iff a non-revoked session token exists."""
    token = read_session_token(entity_root)
    if token is None:
        return False
    return "revoked_at" not in token


# ---------------------------------------------------------------------------
# Integrity Log (§10, §10.6)
# ---------------------------------------------------------------------------

def append_integrity_log(
    entity_root: str | Path,
    envelope:    ACPEnvelope,
) -> None:
    """Append *envelope* to ``state/integrity.log``."""
    append_jsonl(
        Path(entity_root) / "state" / "integrity.log",
        envelope.to_dict(),
    )


def write_heartbeat(
    entity_root: str | Path,
    gseq_counter: GseqCounter,
    session_id:   str = "",
) -> ACPEnvelope:
    """Write a HEARTBEAT envelope to ``state/integrity.log``.

    Args:
        entity_root:  Entity root path.
        gseq_counter: SIL's gseq counter for this session.
        session_id:   Active session ID (included in data payload).

    Returns:
        The written ACPEnvelope.
    """
    data = json.dumps({"session_id": session_id, "ts": utcnow_iso()})
    env = build_envelope(
        actor=ACTOR_SIL,
        type_=TYPE_HEARTBEAT,
        data=data,
        gseq=gseq_counter.next(),
    )
    append_integrity_log(entity_root, env)
    return env


def write_sleep_complete(
    entity_root:  str | Path,
    gseq_counter: GseqCounter,
    session_id:   str = "",
) -> ACPEnvelope:
    """Write a SLEEP_COMPLETE envelope to ``state/integrity.log``.

    This record is the authoritative Sleep Cycle completion boundary
    used by crash recovery (§7.4 / §5.2).
    """
    data = json.dumps({"session_id": session_id, "ts": utcnow_iso()})
    env = build_envelope(
        actor=ACTOR_SIL,
        type_=TYPE_SLEEP_COMPLETE,
        data=data,
        gseq=gseq_counter.next(),
    )
    append_integrity_log(entity_root, env)
    return env


# ---------------------------------------------------------------------------
# Distress Beacon (§10.7)
# ---------------------------------------------------------------------------

BEACON_PATH_REL = "state/distress.beacon"


def check_distress_beacon(entity_root: str | Path) -> bool:
    """Return True iff the Passive Distress Beacon is active."""
    return (Path(entity_root) / BEACON_PATH_REL).exists()


def activate_distress_beacon(entity_root: str | Path, reason: str) -> None:
    """Write the Passive Distress Beacon file with *reason*."""
    beacon_path = Path(entity_root) / BEACON_PATH_REL
    beacon_path.parent.mkdir(parents=True, exist_ok=True)
    beacon_path.write_text(
        json.dumps({"activated_at": utcnow_iso(), "reason": reason}, indent=2),
        encoding="utf-8",
    )


def clear_distress_beacon(entity_root: str | Path) -> None:
    """Remove the Passive Distress Beacon (Operator must call this)."""
    (Path(entity_root) / BEACON_PATH_REL).unlink(missing_ok=True)


def read_distress_beacon(entity_root: str | Path) -> dict[str, Any] | None:
    """Return beacon content or None if not active."""
    path = Path(entity_root) / BEACON_PATH_REL
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"raw": path.read_text(encoding="utf-8", errors="replace")}


# ---------------------------------------------------------------------------
# Crash counter (§5.2)
# ---------------------------------------------------------------------------

def get_crash_counter(entity_root: str | Path) -> int:
    """Count consecutive crash entries in integrity.log since last clean boot.

    A 'crash' is a session token present at boot with no SLEEP_COMPLETE
    between the previous SLEEP_COMPLETE and now.  This is a simplified
    approximation — full Fase 2 implementation will do proper event parsing.
    """
    entries = read_jsonl(Path(entity_root) / "state" / "integrity.log")
    count = 0
    for entry in reversed(entries):
        t = entry.get("type")
        if t == TYPE_SLEEP_COMPLETE:
            break
        if t == "CRASH_RECOVERY":
            count += 1
    return count


def record_crash_recovery(
    entity_root:  str | Path,
    gseq_counter: GseqCounter,
    detail:       str = "",
) -> None:
    """Append a CRASH_RECOVERY marker to the integrity log."""
    data = json.dumps({"detail": detail, "ts": utcnow_iso()})
    env = build_envelope(
        actor=ACTOR_SIL,
        type_="CRASH_RECOVERY",
        data=data,
        gseq=gseq_counter.next(),
    )
    append_integrity_log(entity_root, env)


# ---------------------------------------------------------------------------
# Unresolved Critical conditions (§5, Phase 6)
# ---------------------------------------------------------------------------

CRITICAL_TYPES = {"DRIFT_FAULT", "ESCALATION_FAILED"}


def has_unresolved_critical(entity_root: str | Path) -> bool:
    """Return True iff any unresolved Critical condition exists in integrity.log.

    A Critical condition is 'resolved' when a CRITICAL_CLEARED envelope
    with a matching reference appears after it in the log.
    """
    entries = read_jsonl(Path(entity_root) / "state" / "integrity.log")

    open_criticals: set[str] = set()   # tx UUIDs of unresolved criticals
    cleared: set[str] = set()

    for entry in entries:
        t = entry.get("type", "")
        if t in CRITICAL_TYPES:
            tx = entry.get("tx", "")
            if tx:
                open_criticals.add(tx)
        elif t == "CRITICAL_CLEARED":
            # data field contains reference to the original tx
            try:
                d = json.loads(entry.get("data", "{}"))
                ref = d.get("cleared_tx", "")
                if ref:
                    cleared.add(ref)
            except Exception:
                pass

    return bool(open_criticals - cleared)


def get_unresolved_criticals(entity_root: str | Path) -> list[dict[str, Any]]:
    """Return all unresolved Critical condition envelopes."""
    entries = read_jsonl(Path(entity_root) / "state" / "integrity.log")

    open_map: dict[str, dict[str, Any]] = {}
    cleared: set[str] = set()

    for entry in entries:
        t = entry.get("type", "")
        if t in CRITICAL_TYPES:
            tx = entry.get("tx", "")
            if tx:
                open_map[tx] = entry
        elif t == "CRITICAL_CLEARED":
            try:
                d = json.loads(entry.get("data", "{}"))
                ref = d.get("cleared_tx", "")
                if ref:
                    cleared.add(ref)
            except Exception:
                pass

    return [v for k, v in open_map.items() if k not in cleared]
