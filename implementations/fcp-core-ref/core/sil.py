"""System Integrity Layer (SIL) — FCP-Core §10 MVP subset.

MVP scope (Fase 1–3):
  - SHA-256 hash computation and Integrity Document build/verify (§10.1)
  - Integrity Chain validation — full chain traversal with prev_hash (§10.1)
  - Session token lifecycle: issue / revoke / remove (§3.5)
  - Integrity Log append (state/integrity.log) (§10)
  - HEARTBEAT envelope write (§10.3, simplified — no background thread)
  - Distress Beacon check and activation (§10.7)
  - Crash counter tracking in integrity.log
  - Evolution Gate: Operator decision → EVOLUTION_AUTH / EVOLUTION_REJECTED (§10.5)
  - Endure Protocol (Stage 3): atomic structural writes, snapshot, skill install (§7.4)

Deferred:
  - Background Heartbeat threading loop
  - Reciprocal SIL Watchdog
  - Full drift detection (NCD/gzip)
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
    TYPE_CTX_SKIP,
    TYPE_CRASH_RECOVERY,
    TYPE_CLOSURE_PAYLOAD,
    TYPE_ENDURE_COMMIT,
    TYPE_EVOLUTION_PROPOSAL,
    TYPE_EVOLUTION_AUTH,
    TYPE_EVOLUTION_REJECTED,
    TYPE_PROPOSAL_PENDING,
    TYPE_HEARTBEAT,
    TYPE_SLEEP_COMPLETE,
    ACTOR_SIL,
    build_envelope,
)
from .fs import (
    atomic_write_json,
    atomic_write_text,
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

    # skills/<name>/manifest.json  +  skills/<name>/<name>.md
    skills_dir = entity_root / "skills"
    if skills_dir.exists():
        for manifest in sorted(skills_dir.glob("*/manifest.json")):
            files.append(manifest)
        for skill_dir in sorted(skills_dir.iterdir()):
            if skill_dir.is_dir():
                narrative = skill_dir / f"{skill_dir.name}.md"
                if narrative.exists():
                    files.append(narrative)

    # skills/lib/<name>/manifest.json  +  skills/lib/<name>/<name>.md
    lib_dir = entity_root / "skills" / "lib"
    if lib_dir.exists():
        for manifest in sorted(lib_dir.glob("*/manifest.json")):
            files.append(manifest)
        for skill_dir in sorted(lib_dir.iterdir()):
            if skill_dir.is_dir():
                narrative = skill_dir / f"{skill_dir.name}.md"
                if narrative.exists():
                    files.append(narrative)

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

def _entry_hash(entry: dict[str, Any]) -> str:
    """Canonical SHA-256 of a chain entry (for prev_hash chaining)."""
    canonical = json.dumps(entry, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


def verify_integrity_chain(entity_root: str | Path) -> tuple[bool, str]:
    """Validate the Integrity Chain.

    Checks:
      - integrity_chain.jsonl exists and is non-empty.
      - First entry is GENESIS_OMEGA with required fields.
      - For each subsequent entry: ``prev_hash`` matches the SHA-256 of
        the preceding entry's canonical JSON (skipped if field absent —
        backwards-compatible with pre-chaining entries).
      - ``seq`` values are monotonically increasing without gaps
        (skipped if field absent).

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

    for i in range(1, len(entries)):
        prev = entries[i - 1]
        cur  = entries[i]

        # seq continuity (if both entries carry the field)
        if "seq" in cur and "seq" in prev:
            if cur["seq"] != prev["seq"] + 1:
                return False, (
                    f"chain gap at entry {i}: seq {prev['seq']} → {cur['seq']}"
                )

        # prev_hash verification (if field present and non-empty)
        if cur.get("prev_hash"):
            expected = _entry_hash(prev)
            if cur["prev_hash"] != expected:
                return False, (
                    f"chain entry {i} prev_hash mismatch "
                    f"(expected {expected[:16]}…, got {cur['prev_hash'][:16]}…)"
                )

    return True, ""


def append_chain_entry(entity_root: str | Path, entry: dict[str, Any]) -> None:
    """Append an entry to ``state/integrity_chain.jsonl``.

    Injects ``seq`` (0-based position) and ``prev_hash`` (SHA-256 of the
    preceding entry's canonical JSON) before writing.  The genesis entry
    (seq=0) gets ``prev_hash = ""``.
    """
    chain_path = Path(entity_root) / "state" / "integrity_chain.jsonl"
    existing = read_jsonl(chain_path) if chain_path.exists() else []

    entry_out = dict(entry)
    entry_out["seq"]      = len(existing)
    entry_out["prev_hash"] = _entry_hash(existing[-1]) if existing else ""

    append_jsonl(chain_path, entry_out)


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


def log_closure_payload(
    entity_root:  str | Path,
    gseq_counter: GseqCounter,
    payload:      dict[str, Any],
) -> ACPEnvelope:
    """Log a closure_payload receipt to ``state/integrity.log``.

    Fase 1 stub: records which fields were present.  Full Fase 2
    implementation routes working_memory to the MIL pointer map and
    writes session_handoff to ``memory/session-handoff.json``.
    """
    data = json.dumps({
        "has_consolidation":  bool(payload.get("consolidation")),
        "has_working_memory": bool(payload.get("working_memory")),
        "has_session_handoff": bool(payload.get("session_handoff")),
        "ts": utcnow_iso(),
    })
    env = build_envelope(
        actor=ACTOR_SIL,
        type_=TYPE_CLOSURE_PAYLOAD,
        data=data,
        gseq=gseq_counter.next(),
    )
    append_integrity_log(entity_root, env)
    return env


def _read_integrity_log(entity_root: str | Path) -> list[Any]:
    """Read and return all entries from ``state/integrity.log``."""
    return read_jsonl(Path(entity_root) / "state" / "integrity.log")


def write_ctx_skip(
    entity_root:  str | Path,
    gseq_counter: GseqCounter,
    data:         dict[str, Any],
) -> ACPEnvelope:
    """Write a CTX_SKIP envelope to ``state/integrity.log`` (§5.1).

    Records that one or more context entries were discarded during Boot
    Phase 5 context assembly.  *data* should include at minimum a ``reason``
    key; ``ts`` is injected automatically.
    """
    payload = json.dumps({"ts": utcnow_iso(), **data})
    env = build_envelope(
        actor=ACTOR_SIL,
        type_=TYPE_CTX_SKIP,
        data=payload,
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
    entries = _read_integrity_log(entity_root)
    count = 0
    for entry in reversed(entries):
        t = entry.get("type")
        if t == TYPE_SLEEP_COMPLETE:
            break
        if t == TYPE_CRASH_RECOVERY:
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
        type_=TYPE_CRASH_RECOVERY,
        data=data,
        gseq=gseq_counter.next(),
    )
    append_integrity_log(entity_root, env)


# ---------------------------------------------------------------------------
# Unresolved Critical conditions (§5, Phase 6)
# ---------------------------------------------------------------------------

CRITICAL_TYPES = {"DRIFT_FAULT", "ESCALATION_FAILED"}


def get_unresolved_criticals(entity_root: str | Path) -> list[dict[str, Any]]:
    """Return all unresolved Critical condition envelopes."""
    entries = _read_integrity_log(entity_root)

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


def has_unresolved_critical(entity_root: str | Path) -> bool:
    """Return True iff any unresolved Critical condition exists in integrity.log."""
    return bool(get_unresolved_criticals(entity_root))


def has_sleep_complete(entity_root: str | Path) -> bool:
    """Return True iff the last significant event in integrity.log is SLEEP_COMPLETE.

    Used at Boot Phase 5 to validate Working Memory before loading (§5.1).
    HEARTBEAT entries are transparent in this scan — they don't interrupt
    the SLEEP_COMPLETE boundary.  Any other entry before SLEEP_COMPLETE
    indicates the previous session did not close cleanly.
    """
    entries = _read_integrity_log(entity_root)
    for entry in reversed(entries):
        t = entry.get("type", "")
        if t == TYPE_SLEEP_COMPLETE:
            return True
        if t == TYPE_HEARTBEAT:
            continue
        return False
    return False


# ---------------------------------------------------------------------------
# Evolution Gate (§10.5)
# ---------------------------------------------------------------------------

def get_pending_proposals(entity_root: str | Path) -> list[dict[str, Any]]:
    """Return all unresolved PROPOSAL_PENDING entries from integrity.log.

    A PROPOSAL_PENDING entry is resolved when a matching EVOLUTION_AUTH or
    EVOLUTION_REJECTED record exists with the same ``proposal_tx`` in its
    data payload.
    """
    entries = _read_integrity_log(entity_root)
    pending: dict[str, dict[str, Any]] = {}   # proposal_tx → entry
    resolved: set[str] = set()

    for entry in entries:
        t = entry.get("type", "")
        try:
            d = json.loads(entry.get("data", "{}"))
        except Exception:
            d = {}
        if t == TYPE_PROPOSAL_PENDING:
            proposal_tx = d.get("proposal_tx", "")
            if proposal_tx:
                pending[proposal_tx] = entry
        elif t in (TYPE_EVOLUTION_AUTH, TYPE_EVOLUTION_REJECTED):
            ref = d.get("proposal_tx", "")
            if ref:
                resolved.add(ref)

    return [v for k, v in pending.items() if k not in resolved]


def write_proposal_pending(
    entity_root:  str | Path,
    gseq_counter: GseqCounter,
    content:      str,
    proposal_tx:  str = "",
) -> ACPEnvelope:
    """Write a PROPOSAL_PENDING envelope to integrity.log.

    Used when the session closes before a terminal prompt can be shown.
    The proposal will be re-presented to the Operator at the next session.
    ``proposal_tx`` is the tx of the original EVOLUTION_PROPOSAL envelope.
    """
    data = json.dumps({
        "content":     content,
        "proposal_tx": proposal_tx,
        "ts":          utcnow_iso(),
    })
    env = build_envelope(
        actor=ACTOR_SIL,
        type_=TYPE_PROPOSAL_PENDING,
        data=data,
        gseq=gseq_counter.next(),
    )
    append_integrity_log(entity_root, env)
    return env


def write_evolution_auth(
    entity_root:    str | Path,
    gseq_counter:   GseqCounter,
    proposal_tx:    str,
    content_digest: str,
    operator_name:  str = "",
) -> ACPEnvelope:
    """Write an EVOLUTION_AUTH envelope to integrity.log.

    Records explicit Operator approval.  *content_digest* is a SHA-256
    digest of the approved proposal content — required for authorization
    chain integrity (§10.5).
    """
    data = json.dumps({
        "proposal_tx":    proposal_tx,
        "content_digest": content_digest,
        "operator":       operator_name,
        "ts":             utcnow_iso(),
    })
    env = build_envelope(
        actor=ACTOR_SIL,
        type_=TYPE_EVOLUTION_AUTH,
        data=data,
        gseq=gseq_counter.next(),
    )
    append_integrity_log(entity_root, env)
    return env


def write_evolution_rejected(
    entity_root:  str | Path,
    gseq_counter: GseqCounter,
    proposal_tx:  str,
) -> ACPEnvelope:
    """Write an EVOLUTION_REJECTED envelope to integrity.log.

    Records explicit Operator rejection.  Outcome is never returned to CPE.
    """
    data = json.dumps({"proposal_tx": proposal_tx, "ts": utcnow_iso()})
    env = build_envelope(
        actor=ACTOR_SIL,
        type_=TYPE_EVOLUTION_REJECTED,
        data=data,
        gseq=gseq_counter.next(),
    )
    append_integrity_log(entity_root, env)
    return env


# ---------------------------------------------------------------------------
# Endure Protocol — Stage 3 (§7.4)
# ---------------------------------------------------------------------------

def _is_skill_install(target_file: str) -> tuple[bool, str]:
    """Return (True, skill_name) if target_file is stage/<name> (cartridge install)."""
    parts = Path(target_file).parts
    if len(parts) == 2 and parts[0] == "stage":
        return True, parts[1]
    return False, ""


def _install_skill_cartridge(
    entity_root:      Path,
    skill_name:       str,
    manifest_content: str,
) -> list[str]:
    """Install cartridge from stage/<skill_name>/ to skills/<skill_name>/.

    Writes manifest.json from manifest_content, copies <skill_name>.md and
    execute.* from stage/.  Returns list of error strings (empty = success).
    """
    import shutil

    stage_dir  = entity_root / "stage"  / skill_name
    skills_dir = entity_root / "skills" / skill_name

    if not stage_dir.exists():
        return [f"stage/{skill_name}/ not found"]

    try:
        json.loads(manifest_content)
    except json.JSONDecodeError as exc:
        return [f"invalid manifest JSON for {skill_name!r}: {exc}"]

    skills_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(skills_dir / "manifest.json", manifest_content)

    # Copy narrative
    narrative_src = stage_dir / f"{skill_name}.md"
    if narrative_src.exists():
        shutil.copy2(narrative_src, skills_dir / f"{skill_name}.md")

    # Copy execute.* (optional)
    for exe_name in ("execute.sh", "execute.py"):
        src = stage_dir / exe_name
        if src.exists():
            dst = skills_dir / exe_name
            shutil.copy2(src, dst)
            dst.chmod(0o755)
            break

    return []


def _take_snapshot(
    entity_root:   Path,
    gseq_counter:  GseqCounter,
    snapshot_keep: int,
) -> str | None:
    """Compress entity_root/ to state/snapshots/<ts>-<gseq>.tar.gz.

    Excludes workspace/, io/, and state/snapshots/ from the archive.
    Rotates to keep at most snapshot_keep archives (0 = unlimited).
    Returns archive name on success, None on failure.
    """
    import tarfile as _tarfile

    _EXCLUDE_TOP = {"workspace", "io"}

    snapshots_dir = entity_root / "state" / "snapshots"
    snapshots_dir.mkdir(parents=True, exist_ok=True)

    ts   = utcnow_iso().replace(":", "").replace("-", "")
    gseq = gseq_counter.next()
    name = f"{ts}-{gseq}.tar.gz"
    dst  = snapshots_dir / name
    tmp  = snapshots_dir / (name + ".tmp")

    def _filter(info: _tarfile.TarInfo) -> _tarfile.TarInfo | None:
        parts = Path(info.name).parts
        if not parts:
            return info
        # arcname="." so parts[0] == ".", top-level dir is parts[1]
        top = parts[1] if parts[0] == "." and len(parts) > 1 else parts[0]
        if top in _EXCLUDE_TOP:
            return None
        # exclude state/snapshots itself
        if len(parts) >= 3 and parts[1] == "state" and parts[2] == "snapshots":
            return None
        return info

    try:
        with _tarfile.open(tmp, "w:gz") as tar:
            tar.add(entity_root, arcname=".", filter=_filter)
        os.rename(tmp, dst)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        return None

    # Rotation
    if snapshot_keep > 0:
        existing = sorted(snapshots_dir.glob("*.tar.gz"))
        for old in existing[:-snapshot_keep]:
            try:
                old.unlink()
            except Exception:
                pass

    return name


def run_endure(
    entity_root:         str | Path,
    gseq_counter:        GseqCounter,
    session_id:          str = "",
    checkpoint_interval: int = 10,
    snapshot_keep:       int = 3,
) -> list[str]:
    """Apply all authorized Evolution Proposals to structural files (§7.4).

    Scans integrity.log for EVOLUTION_AUTH records with no matching
    ENDURE_COMMIT, then for each:
      1. Takes a compressed snapshot of entity_root/ before the first write.
      2. Verifies content_digest against SHA-256 of proposal content.
      3. Validates target_file is a tracked structural file (security gate).
         New skill manifests (skills/<name>/manifest.json) are also allowed.
      4. Writes content atomically to target_file.
      5. For skill installs: copies run.sh from stage/, rebuilds index, cleans stage/.
      6. Rebuilds and writes the Integrity Document.
      7. Logs ENDURE_COMMIT to integrity.log.
      8. Checkpoints the Integrity Chain if interval is reached.

    Returns a list of error strings (empty = success).
    """
    entity_root = Path(entity_root)
    entries = _read_integrity_log(entity_root)

    # Build maps in a single pass
    proposals: dict[str, dict[str, Any]] = {}   # envelope_tx → data
    auths:     dict[str, dict[str, Any]] = {}   # proposal_tx → auth_data
    committed: set[str] = set()                 # proposal_tx already ENDURE_COMMITted

    for entry in entries:
        t  = entry.get("type", "")
        tx = entry.get("tx", "")
        try:
            d = json.loads(entry.get("data", "{}"))
        except Exception:
            d = {}

        if t == TYPE_EVOLUTION_PROPOSAL and tx:
            proposals[tx] = d
        elif t == TYPE_EVOLUTION_AUTH:
            ptx = d.get("proposal_tx", "")
            if ptx:
                auths[ptx] = d
        elif t == TYPE_ENDURE_COMMIT:
            ptx = d.get("proposal_tx", "")
            if ptx:
                committed.add(ptx)

    allowed = {str(f.relative_to(entity_root)) for f in _tracked_files(entity_root)}
    errors: list[str] = []
    commit_count = len(committed)

    # Take snapshot before any structural writes (once per run_endure call)
    pending = [tx for tx in auths if tx not in committed]
    if pending:
        _take_snapshot(entity_root, gseq_counter, snapshot_keep)

    for proposal_tx, auth_data in auths.items():
        if proposal_tx in committed:
            continue   # already applied

        proposal_data = proposals.get(proposal_tx)
        if proposal_data is None:
            errors.append(
                f"EVOLUTION_AUTH {proposal_tx[:8]}… has no matching EVOLUTION_PROPOSAL"
            )
            continue

        content     = proposal_data.get("content", "")
        target_file = proposal_data.get("target_file", "")
        is_skill, skill_name = _is_skill_install(target_file)

        # Verify digest
        actual_digest = hashlib.sha256(content.encode()).hexdigest()
        if actual_digest != auth_data.get("content_digest", ""):
            errors.append(
                f"content_digest mismatch for proposal {proposal_tx[:8]}…"
                f" (target: {target_file!r})"
            )
            continue

        # Security gate (skill installs bypass file-path check)
        if not is_skill and target_file not in allowed:
            errors.append(
                f"target_file {target_file!r} is not a tracked structural file — rejected"
            )
            continue

        # Write
        if is_skill:
            errs = _install_skill_cartridge(entity_root, skill_name, content)
            if errs:
                errors.extend(errs)
                continue
        else:
            try:
                atomic_write_text(entity_root / target_file, content)
            except Exception as exc:
                errors.append(f"write failed for {target_file!r}: {exc}")
                continue

        # Rebuild Integrity Document
        new_doc = build_integrity_document(entity_root)
        write_integrity_document(entity_root, new_doc)

        # Skill post-install: rebuild index, re-snapshot integrity doc, clean stage/
        if is_skill:
            import shutil
            from .exec_ import build_skill_index
            from .fs import atomic_write_json as _awj
            new_index = build_skill_index(entity_root)
            _awj(entity_root / "skills" / "index.json", new_index)
            new_doc = build_integrity_document(entity_root)
            write_integrity_document(entity_root, new_doc)
            stage_dir = entity_root / "stage" / skill_name
            if stage_dir.exists():
                shutil.rmtree(stage_dir)

        # Log ENDURE_COMMIT
        _write_endure_commit(entity_root, gseq_counter, proposal_tx, target_file)
        commit_count += 1

        # Integrity Chain checkpoint
        if checkpoint_interval > 0 and commit_count % checkpoint_interval == 0:
            _write_endure_checkpoint(entity_root, gseq_counter, commit_count)

    return errors


def _write_endure_commit(
    entity_root:  str | Path,
    gseq_counter: GseqCounter,
    proposal_tx:  str,
    target_file:  str,
) -> ACPEnvelope:
    """Append an ENDURE_COMMIT envelope to integrity.log."""
    data = json.dumps({
        "proposal_tx": proposal_tx,
        "target_file": target_file,
        "ts":          utcnow_iso(),
    })
    env = build_envelope(
        actor=ACTOR_SIL,
        type_=TYPE_ENDURE_COMMIT,
        data=data,
        gseq=gseq_counter.next(),
    )
    append_integrity_log(entity_root, env)
    return env


def _write_endure_checkpoint(
    entity_root:  str | Path,
    gseq_counter: GseqCounter,
    commit_count: int,
) -> None:
    """Append an ENDURE_CHECKPOINT entry to the Integrity Chain."""
    doc_path   = Path(entity_root) / "state" / "integrity.json"
    doc_digest = compute_file_hash(doc_path) if doc_path.exists() else ""
    append_chain_entry(entity_root, {
        "type":          "ENDURE_CHECKPOINT",
        "integrity_doc": doc_digest,
        "commit_count":  commit_count,
        "ts":            utcnow_iso(),
    })
