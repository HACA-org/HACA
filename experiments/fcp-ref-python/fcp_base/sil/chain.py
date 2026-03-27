"""
SIL integrity chain, evolution auth, skill index, and integrity log writers.

Covers:
  - Integrity chain append / last seq query
  - Evolution auth record
  - Integrity log ACP envelope writers (heartbeat, critical, etc.)
  - Skill index build (FAP §4)
"""

from __future__ import annotations

import json
import time
import uuid
from typing import TYPE_CHECKING, Any

from ..acp import ACPEnvelope, crc32, make as _acp_make
from ..formats import (
    AliasEntry,
    ChainEntry,
    SkillClass,
    SkillEntry,
    SkillIndex,
    SkillManifest,
)
from ..store import append_jsonl, atomic_write, read_json, read_jsonl
from .utils import utcnow

if TYPE_CHECKING:
    from ..store import Layout


# ---------------------------------------------------------------------------
# Integrity Log helpers
# ---------------------------------------------------------------------------

def _log_envelope(layout: "Layout", actor: str, type_: str, data: str) -> None:
    """Append a single ACP envelope to state/integrity.log."""
    ts = utcnow()
    env = ACPEnvelope(
        actor=actor,
        gseq=0,
        tx=str(uuid.uuid4()),
        seq=1,
        eof=True,
        type=type_,
        ts=ts,
        data=data,
        crc=crc32(data),
    )
    append_jsonl(layout.integrity_log, env.to_dict())


def log_heartbeat(layout: "Layout", session_id: str) -> None:
    _log_envelope(layout, "sil", "HEARTBEAT", json.dumps({"session_id": session_id}))


def log_critical(layout: "Layout", type_: str, detail: dict[str, Any]) -> None:
    _log_envelope(layout, "sil", type_, json.dumps(detail))


def log_severance_commit(layout: "Layout", skill_name: str, issues: list[str]) -> None:
    _log_envelope(layout, "sil", "SEVERANCE_COMMIT", json.dumps({
        "skill": skill_name,
        "issues": issues,
    }))


def log_cleared(layout: "Layout", original_seq: int) -> None:
    _log_envelope(
        layout, "sil", "CRITICAL_CLEARED",
        json.dumps({"clears_seq": original_seq, "ts": utcnow()}),
    )


def log_sleep_complete(layout: "Layout", session_id: str) -> None:
    _log_envelope(
        layout, "sil", "SLEEP_COMPLETE",
        json.dumps({"session_id": session_id, "ts": utcnow()}),
    )


def log_acp_envelope(layout: "Layout", env: ACPEnvelope) -> None:
    """Append a pre-built ACPEnvelope to integrity.log."""
    append_jsonl(layout.integrity_log, env.to_dict())


def write_evolution_auth(layout: "Layout", content: str, auth_digest: str) -> None:
    """Write an EVOLUTION_AUTH record to state/integrity.log."""
    ts = int(time.time() * 1000)
    try:
        parsed_content = json.loads(content)
    except Exception:
        parsed_content = content
    envelope = _acp_make(
        env_type="MSG",
        source="operator",
        data={"type": "EVOLUTION_AUTH", "auth_digest": auth_digest, "content": parsed_content, "ts": ts},
    )
    append_jsonl(layout.integrity_log, envelope)


# ---------------------------------------------------------------------------
# Integrity Chain
# ---------------------------------------------------------------------------

def write_chain_entry(layout: "Layout", entry: ChainEntry) -> None:
    """Append *entry* to state/integrity_chain.jsonl."""
    append_jsonl(layout.integrity_chain, entry.to_dict())


def last_chain_seq(layout: "Layout") -> int:
    """Return the highest seq in the integrity chain, or 0 if empty."""
    entries = read_jsonl(layout.integrity_chain)
    if not entries:
        return 0
    seqs = [e.get("seq", 0) for e in entries]
    return int(max(seqs))


# ---------------------------------------------------------------------------
# §4 FAP — Skill Index
# ---------------------------------------------------------------------------

def build_skill_index(layout: "Layout") -> SkillIndex:
    """Scan skills/ and build a validated SkillIndex.

    Only skills with a present executable and a well-formed manifest are
    included.  Writes skills/index.json atomically.
    """
    entries: list[SkillEntry] = []

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
