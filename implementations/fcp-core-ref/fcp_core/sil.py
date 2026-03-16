"""
System Integrity Layer — structural primitives.  §10

This module contains the stateless SIL operations used by FAP and the Boot
Sequence.  The session-bound behaviour (Heartbeat loop, Vital Check, Watchdog)
is driven by the session loop in session.py and calls into this module for
the actual verification and write logic.

§10.1  Structural Verification
§10.2  Drift Detection (detection helpers only; loop belongs in session.py)
§10.5  Evolution Gate (write helpers)
§10.6  Operator Channel (notification write)
§10.7  Passive Distress Beacon
§10.8  Critical Condition Resolution (write helpers)
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .acp import ACPEnvelope, crc32
from .formats import (
    AliasEntry,
    BeaconCause,
    ChainEntry,
    ChainEntryType,
    IntegrityDocument,
    SessionToken,
    SkillClass,
    SkillEntry,
    SkillIndex,
    SkillManifest,
)
from .store import Layout, append_jsonl, atomic_write, read_json, read_jsonl


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path: Path) -> str:
    """Return 'sha256:<hex>' digest of *path* contents."""
    h = hashlib.sha256(path.read_bytes())
    return f"sha256:{h.hexdigest()}"


def sha256_str(text: str) -> str:
    """Return 'sha256:<hex>' digest of *text* encoded as UTF-8."""
    h = hashlib.sha256(text.encode())
    return f"sha256:{h.hexdigest()}"


def sha256_bytes(data: bytes) -> str:
    """Return 'sha256:<hex>' digest of raw bytes."""
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


# ---------------------------------------------------------------------------
# Tracked structural files
# ---------------------------------------------------------------------------

def tracked_files(layout: Layout) -> list[Path]:
    """Return all files that must be present in the Integrity Document.

    Covers: boot.md, all persona/ files, state/baseline.json,
    skills/index.json, and all skill manifest.json files found under
    skills/.  Does NOT include volatile runtime artefacts.
    """
    paths: list[Path] = [layout.boot_md, layout.baseline, layout.skills_index]

    if layout.persona_dir.is_dir():
        paths.extend(sorted(layout.persona_dir.iterdir()))

    # skill manifests: skills/<name>/manifest.json (custom/operator)
    # and skills/lib/<name>/manifest.json (builtin)
    for manifest in sorted(layout.skills_dir.glob("*/manifest.json")):
        paths.append(manifest)
    for manifest in sorted(layout.skills_lib_dir.glob("*/manifest.json")):
        paths.append(manifest)

    return [p for p in paths if p.is_file()]


# ---------------------------------------------------------------------------
# §10.1 Structural Verification
# ---------------------------------------------------------------------------

def compute_integrity_files(layout: Layout) -> dict[str, str]:
    """Compute SHA-256 hashes for all tracked structural files.

    Returns a dict mapping path-relative-to-entity-root → 'sha256:<hex>'.
    """
    result: dict[str, str] = {}
    for p in tracked_files(layout):
        rel = str(p.relative_to(layout.root))
        result[rel] = sha256_file(p)
    return result


def write_integrity_doc(layout: Layout, files: dict[str, str]) -> None:
    """Write state/integrity.json atomically with the given file hashes."""
    doc = IntegrityDocument(
        version="1.0",
        algorithm="sha256",
        last_checkpoint=None,
        files=files,
    )
    atomic_write(layout.integrity_doc, doc.to_dict())


def verify_structural_files(
    layout: Layout, integrity_doc: IntegrityDocument
) -> list[str]:
    """Recompute hashes and compare against *integrity_doc*.

    Returns a list of mismatch descriptions.  Empty list means clean.
    """
    mismatches: list[str] = []
    for rel, expected in integrity_doc.files.items():
        p = layout.root / rel
        if not p.exists():
            mismatches.append(f"missing: {rel}")
            continue
        actual = sha256_file(p)
        if actual != expected:
            mismatches.append(f"hash mismatch: {rel}")
    return mismatches


def verify_integrity_chain(layout: Layout, integrity_doc: IntegrityDocument) -> bool:
    """Validate the integrity chain from the last checkpoint forward.

    Returns True if valid, False if any gap, hash mismatch, or missing
    authorization reference is detected.
    """
    if not layout.integrity_chain.exists():
        return False

    entries = read_jsonl(layout.integrity_chain)
    if not entries:
        return False

    cp = integrity_doc.last_checkpoint
    start_seq = cp.seq if cp is not None else 0

    # Build a map seq → raw line for hash verification.
    lines = layout.integrity_chain.read_text(encoding="utf-8").splitlines()
    seq_to_line: dict[int, str] = {}
    for line in lines:
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        seq_to_line[d["seq"]] = line

    # Validate from genesis (seq=1) or from checkpoint.
    check_from = 1 if cp is None else start_seq
    prev_hash: str | None = None

    for seq in sorted(seq_to_line.keys()):
        if seq < check_from:
            continue
        raw = seq_to_line[seq]
        entry = ChainEntry.from_dict(json.loads(raw))

        if entry.type == ChainEntryType.GENESIS:
            if entry.imprint_hash is None:
                return False
        else:
            # Every non-genesis entry must reference prev_hash.
            if prev_hash is not None and entry.prev_hash != prev_hash:
                return False
            # ENDURE_COMMIT must have evolution_auth_digest.
            if entry.type == ChainEntryType.ENDURE_COMMIT:
                if not entry.evolution_auth_digest:
                    return False

        prev_hash = sha256_str(raw)

    # If a checkpoint was declared, verify its digest matches.
    cp_final = cp
    if cp_final is not None:
        raw_cp = seq_to_line.get(cp_final.seq)
        if raw_cp is None:
            return False
        actual_digest = sha256_str(raw_cp)
        if actual_digest != cp_final.digest:
            return False

    # P7 — Evolutionary Drift: every ENDURE_COMMIT's evolution_auth_digest must
    # correspond to an actual EVOLUTION_AUTH record in the integrity log.
    if not _verify_evolution_auth_coverage(layout, entries):
        return False

    return True


def _verify_evolution_auth_coverage(layout: Layout, chain_entries: list[dict]) -> bool:
    """Check that each ENDURE_COMMIT in the chain has a matching EVOLUTION_AUTH
    in integrity.log, and that each EVOLUTION_AUTH references the previous chain entry.

    Returns True if all ENDURE_COMMITs are covered, False otherwise.
    """
    # Collect auth_digests from EVOLUTION_AUTH records in integrity.log.
    # EVOLUTION_AUTH is written as an ACP envelope (type="MSG"), with the
    # actual type inside the data JSON field.
    auth_digests: set[str] = set()
    if layout.integrity_log.exists():
        for log_entry in read_jsonl(layout.integrity_log):
            try:
                data = json.loads(log_entry.get("data", "{}"))
            except (json.JSONDecodeError, TypeError):
                continue
            if data.get("type") != "EVOLUTION_AUTH":
                continue
            digest = data.get("auth_digest", "")
            if digest:
                auth_digests.add(digest)

    # Every ENDURE_COMMIT must have its evolution_auth_digest covered
    for raw_entry in chain_entries:
        entry = ChainEntry.from_dict(raw_entry)
        if entry.type != ChainEntryType.ENDURE_COMMIT:
            continue
        if not entry.evolution_auth_digest:
            return False
        if entry.evolution_auth_digest not in auth_digests:
            return False

    return True


# ---------------------------------------------------------------------------
# §10.7 Passive Distress Beacon
# ---------------------------------------------------------------------------

def activate_beacon(
    layout: Layout, cause: str, consecutive_failures: int
) -> None:
    """Write state/distress.beacon atomically."""
    atomic_write(
        layout.distress_beacon,
        {
            "cause": cause,
            "ts": _utcnow(),
            "consecutive_failures": consecutive_failures,
        },
    )
    from .hooks import run_hook
    run_hook(layout, "on_beacon_activated", {
        "cause": cause,
        "consecutive_failures": consecutive_failures,
    })


def beacon_is_active(layout: Layout) -> bool:
    return layout.distress_beacon.exists()


def clear_beacon(layout: Layout) -> None:
    """Remove state/distress.beacon.  Only called after Operator + SIL confirm."""
    if layout.distress_beacon.exists():
        layout.distress_beacon.unlink()


# ---------------------------------------------------------------------------
# §5.3 Session Token
# ---------------------------------------------------------------------------

def issue_session_token(layout: Layout) -> str:
    """Write state/sentinels/session.token and return the new session_id."""
    session_id = str(uuid.uuid4())
    token = SessionToken(session_id=session_id, issued_at=_utcnow(), revoked_at=None)
    layout.sentinels_dir.mkdir(parents=True, exist_ok=True)
    atomic_write(layout.session_token, token.to_dict())
    return session_id


def revoke_session_token(layout: Layout) -> None:
    """Stamp revoked_at on the session token atomically."""
    if not layout.session_token.exists():
        return
    d = read_json(layout.session_token)
    d["revoked_at"] = _utcnow()
    atomic_write(layout.session_token, d)


def session_token_present(layout: Layout) -> bool:
    return layout.session_token.exists()


def read_session_token(layout: Layout) -> SessionToken | None:
    if not layout.session_token.exists():
        return None
    return SessionToken.from_dict(read_json(layout.session_token))


# ---------------------------------------------------------------------------
# §10.6 Operator Channel — notification write
# ---------------------------------------------------------------------------

def write_notification(
    layout: Layout,
    severity: str,
    payload: dict[str, Any],
) -> Path:
    """Write a notification file to state/operator_notifications/.

    Filename format: <utc-timestamp>.<severity>.json
    (colons in timestamp replaced with hyphens per §10.6).

    Returns the path written.
    """
    ts = _utcnow().replace(":", "-")
    name = f"{ts}.{severity}.json"
    path = layout.operator_notifications_dir / name
    layout.operator_notifications_dir.mkdir(parents=True, exist_ok=True)
    atomic_write(path, payload)
    return path


# ---------------------------------------------------------------------------
# Integrity Log — ACP envelope append
# ---------------------------------------------------------------------------

def _log_envelope(layout: Layout, actor: str, type_: str, data: str) -> None:
    """Append a single ACP envelope to state/integrity.log."""
    ts = _utcnow()
    env = ACPEnvelope(
        actor=actor,
        gseq=0,       # integrity log entries are not part of a gseq chain
        tx=str(uuid.uuid4()),
        seq=1,
        eof=True,
        type=type_,
        ts=ts,
        data=data,
        crc=crc32(data),
    )
    append_jsonl(layout.integrity_log, env.to_dict())


def log_heartbeat(layout: Layout, session_id: str) -> None:
    _log_envelope(layout, "sil", "HEARTBEAT", json.dumps({"session_id": session_id}))


def log_critical(layout: Layout, type_: str, detail: dict[str, Any]) -> None:
    _log_envelope(layout, "sil", type_, json.dumps(detail))


def log_severance_commit(layout: Layout, skill_name: str, issues: list[str]) -> None:
    _log_envelope(layout, "sil", "SEVERANCE_COMMIT", json.dumps({
        "skill": skill_name,
        "issues": issues,
    }))


def log_cleared(layout: Layout, original_seq: int) -> None:
    _log_envelope(
        layout, "sil", "CRITICAL_CLEARED",
        json.dumps({"clears_seq": original_seq, "ts": _utcnow()}),
    )


def log_sleep_complete(layout: Layout, session_id: str) -> None:
    _log_envelope(
        layout, "sil", "SLEEP_COMPLETE",
        json.dumps({"session_id": session_id, "ts": _utcnow()}),
    )


def log_acp_envelope(layout: Layout, env: ACPEnvelope) -> None:
    """Append a pre-built ACPEnvelope to integrity.log."""
    append_jsonl(layout.integrity_log, env.to_dict())


# ---------------------------------------------------------------------------
# Integrity Chain
# ---------------------------------------------------------------------------

def write_chain_entry(layout: Layout, entry: ChainEntry) -> None:
    """Append *entry* to state/integrity_chain.jsonl."""
    append_jsonl(layout.integrity_chain, entry.to_dict())


def last_chain_seq(layout: Layout) -> int:
    """Return the highest seq in the integrity chain, or 0 if empty."""
    entries = read_jsonl(layout.integrity_chain)
    if not entries:
        return 0
    seqs = [e.get("seq", 0) for e in entries]
    seq = max(seqs)
    return int(seq)


# ---------------------------------------------------------------------------
# §4 FAP — Skill Index validation
# ---------------------------------------------------------------------------

def build_skill_index(layout: Layout) -> SkillIndex:
    """Scan skills/ and build a validated SkillIndex.

    Only skills with a present executable and a well-formed manifest are
    included.  Writes skills/index.json atomically.
    """
    entries: list[SkillEntry] = []

    # builtin skills: skills/lib/<name>/manifest.json
    if layout.skills_lib_dir.is_dir():
        for manifest_path in sorted(layout.skills_lib_dir.glob("*/manifest.json")):
            try:
                m = SkillManifest.from_dict(read_json(manifest_path))
                exe = manifest_path.parent / "run.py"
                if exe.exists():
                    entries.append(SkillEntry(
                        name=m.name,
                        desc=m.description,
                        manifest=str(manifest_path.relative_to(layout.root)),
                        cls=SkillClass.BUILTIN,
                    ))
            except (KeyError, TypeError, ValueError):
                pass

    # custom / operator skills: skills/<name>/manifest.json
    if layout.skills_dir.is_dir():
        for manifest_path in sorted(layout.skills_dir.glob("*/manifest.json")):
            if "lib" in manifest_path.parts:
                continue
            try:
                m = SkillManifest.from_dict(read_json(manifest_path))
                exe = manifest_path.parent / "run.py"
                if exe.exists():
                    cls = (
                        SkillClass.OPERATOR
                        if m.cls == SkillClass.OPERATOR
                        else SkillClass.CUSTOM
                    )
                    entries.append(SkillEntry(
                        name=m.name,
                        desc=m.description,
                        manifest=str(manifest_path.relative_to(layout.root)),
                        cls=cls,
                    ))
            except (KeyError, TypeError, ValueError):
                pass

    index = SkillIndex(version="1.0", skills=entries, aliases={})
    atomic_write(layout.skills_index, index.to_dict())
    return index


# ---------------------------------------------------------------------------
# Operator Channel availability check
# ---------------------------------------------------------------------------

def operator_channel_available(layout: Layout) -> tuple[bool, bool]:
    """Return (notifications_writable, terminal_available).

    terminal_available is True when stdin is a tty or when running in a
    context where input() can be called (best-effort check).
    """
    import sys

    notif_ok = False
    try:
        layout.operator_notifications_dir.mkdir(parents=True, exist_ok=True)
        test = layout.operator_notifications_dir / ".write_test"
        test.write_text("x", encoding="utf-8")
        test.unlink()
        notif_ok = True
    except OSError:
        pass

    terminal_ok = sys.stdin.isatty()

    return notif_ok, terminal_ok
