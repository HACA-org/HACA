"""
SIL structural verification — §10.1.

Tracks structural files, computes and verifies SHA-256 integrity documents,
and validates the integrity chain (including evolution auth coverage).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from ..acp import parse_envelope_data
from ..formats import ChainEntry, ChainEntryType, IntegrityDocument
from ..store import atomic_write, read_jsonl
from .utils import sha256_file, sha256_str

if TYPE_CHECKING:
    from ..store import Layout


def tracked_files(layout: "Layout") -> list:
    """Return all files that must be present in the Integrity Document."""
    from pathlib import Path
    paths: list[Path] = [layout.boot_md, layout.baseline, layout.skills_index]

    if layout.persona_dir.is_dir():
        paths.extend(sorted(layout.persona_dir.iterdir()))

    for manifest in sorted(layout.skills_dir.glob("*/manifest.json")):
        paths.append(manifest)
    for manifest in sorted(layout.skills_lib_dir.glob("*/manifest.json")):
        paths.append(manifest)

    return [p for p in paths if p.is_file()]


def compute_integrity_files(layout: "Layout") -> dict[str, str]:
    """Compute SHA-256 hashes for all tracked structural files."""
    result: dict[str, str] = {}
    for p in tracked_files(layout):
        rel = str(p.relative_to(layout.root))
        result[rel] = sha256_file(p)
    return result


def write_integrity_doc(layout: "Layout", files: dict[str, str]) -> None:
    """Write state/integrity.json atomically with the given file hashes."""
    doc = IntegrityDocument(
        version="1.0",
        algorithm="sha256",
        last_checkpoint=None,
        files=files,
    )
    atomic_write(layout.integrity_doc, doc.to_dict())


def verify_structural_files(
    layout: "Layout", integrity_doc: IntegrityDocument
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


def verify_integrity_chain(layout: "Layout", integrity_doc: IntegrityDocument) -> bool:
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

    lines = layout.integrity_chain.read_text(encoding="utf-8").splitlines()
    seq_to_line: dict[int, str] = {}
    for line in lines:
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        seq_to_line[d["seq"]] = line

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
            if prev_hash is not None and entry.prev_hash != prev_hash:
                return False
            if entry.type == ChainEntryType.ENDURE_COMMIT:
                if not entry.evolution_auth_digest:
                    return False

        prev_hash = sha256_str(raw)

    cp_final = cp
    if cp_final is not None:
        raw_cp = seq_to_line.get(cp_final.seq)
        if raw_cp is None:
            return False
        actual_digest = sha256_str(raw_cp)
        if actual_digest != cp_final.digest:
            return False

    if not _verify_evolution_auth_coverage(layout, entries):
        return False

    return True


def _verify_evolution_auth_coverage(layout: "Layout", chain_entries: list[dict]) -> bool:
    """Check that each ENDURE_COMMIT in the chain has a matching EVOLUTION_AUTH."""
    auth_digests: set[str] = set()
    if layout.integrity_log.exists():
        for log_entry in read_jsonl(layout.integrity_log):
            data = parse_envelope_data(log_entry)
            if data.get("type") != "EVOLUTION_AUTH":
                continue
            digest = data.get("auth_digest", "")
            if digest:
                auth_digests.add(digest)

    for raw_entry in chain_entries:
        entry = ChainEntry.from_dict(raw_entry)
        if entry.type != ChainEntryType.ENDURE_COMMIT:
            continue
        if not entry.evolution_auth_digest:
            return False
        if entry.evolution_auth_digest not in auth_digests:
            return False

    return True
