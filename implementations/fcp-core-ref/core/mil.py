"""Memory Interface Layer (MIL) — FCP-Core §8.

The MIL has full authority over memory/ — it is the sole component authorized
to read and write the Memory Store.  Write routing depends on the caller context:

  CPE mid-session (memory_write action):
    Writes go to memory/episodic/ — free mnemonic writes, no authorization needed.

  Session close (closure_payload processing — Sleep Cycle Stage 1):
    Consolidation content → memory/episodic/ (label="consolidation") + session.jsonl.
    Working memory pointer map → working-memory.json.
    Session handoff → session-handoff.json.

Fase 2 scope (now included):
  - memory_write: persist CPE mnemonic content to memory/episodic/
  - memory_recall: search all memory/ .md artifacts by substring
  - append_to_session_store: direct write to session.jsonl (used by FCP orchestrator)
  - write_working_memory: write working-memory.json (Sleep Cycle Stage 1)
  - write_session_handoff: write session-handoff.json (Sleep Cycle Stage 1)

Deferred to Fase 3:
  - Sleep Cycle Stage 2 (Garbage Collection / session store rotation)
  - Pre-session buffer overflow handling
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from .acp import (
    ACPEnvelope,
    GseqCounter,
    ACTOR_MIL,
    TYPE_MEMO_RESULT,
    chunk_payload,
)
from .fs import (
    atomic_write_json,
    append_jsonl,
    read_json,
    read_jsonl,
    spool_msg,
    utcnow_iso,
)


# ---------------------------------------------------------------------------
# Session Store (§8.1)
# ---------------------------------------------------------------------------

def append_to_session_store(
    entity_root: str | Path,
    envelope:    ACPEnvelope,
) -> None:
    """Append *envelope* to ``memory/session.jsonl``.

    The MIL is the sole writer to session.jsonl.  The FCP orchestrator
    calls this after draining io/inbox/ at the start of each cycle.
    """
    append_jsonl(
        Path(entity_root) / "memory" / "session.jsonl",
        envelope.to_dict(),
    )


def read_session_tail(
    entity_root:  str | Path,
    max_entries:  int = 200,
) -> list[dict[str, Any]]:
    """Return the tail of session.jsonl (newest entries last, up to max_entries)."""
    entries = read_jsonl(Path(entity_root) / "memory" / "session.jsonl")
    return entries[-max_entries:]


# ---------------------------------------------------------------------------
# Memory Store writes — memory_write action (§6.2)
# ---------------------------------------------------------------------------

def write_episodic(
    entity_root: str | Path,
    content:     str,
    label:       str = "",
) -> Path:
    """Write *content* to a new file in ``memory/episodic/`` and return the path.

    Pure write — no inbox notification.  Used for internal MIL operations
    (e.g. Sleep Cycle Stage 1 consolidation) where CPE feedback is not needed.
    """
    entity_root = Path(entity_root)
    episodic_dir = entity_root / "memory" / "episodic"
    episodic_dir.mkdir(parents=True, exist_ok=True)

    ts_compact = utcnow_iso().replace(":", "").replace("-", "")
    uid = uuid.uuid4().hex[:8]
    filename = f"{ts_compact}-{uid}"
    if label:
        safe_label = "".join(c if c.isalnum() or c in "-_" else "_" for c in label)[:40]
        filename += f"-{safe_label}"
    filename += ".md"

    mem_path = episodic_dir / filename
    mem_path.write_text(content, encoding="utf-8")
    return mem_path


def memory_write(
    entity_root:  str | Path,
    content:      str,
    gseq_counter: GseqCounter,
    label:        str = "",
) -> list[dict[str, Any]]:
    """Write *content* to a new file in ``memory/episodic/`` and notify CPE via inbox.

    Steps:
      1. Create a unique .md file in memory/episodic/ via write_episodic.
      2. Write a MEMO_RESULT envelope to io/inbox/ so the CPE learns
         the write succeeded.

    Args:
        entity_root:  Entity root path.
        content:      Text to persist (session note, task context, recalled fact).
        gseq_counter: MIL's gseq counter for this session.
        label:        Optional short label used in the filename.

    Returns:
        List of ACP envelope dicts written to io/inbox/.
    """
    mem_path    = write_episodic(entity_root, content, label)
    entity_root = Path(entity_root)

    rel_path    = str(mem_path.relative_to(entity_root))
    result_data = json.dumps({"status": "ok", "path": rel_path, "ts": utcnow_iso()})

    envelopes = chunk_payload(
        actor=ACTOR_MIL,
        type_=TYPE_MEMO_RESULT,
        payload_str=result_data,
        gseq_start=gseq_counter.next(),
    )

    inbox_envelopes: list[dict[str, Any]] = []
    for env in envelopes:
        spool_msg(entity_root, env.to_dict())
        inbox_envelopes.append(env.to_dict())
        if not env.eof:
            gseq_counter._value = env.gseq  # keep counter in sync for multi-chunk

    return inbox_envelopes


# ---------------------------------------------------------------------------
# Memory Store reads — memory_recall action (§6.2)
# ---------------------------------------------------------------------------

def memory_recall(
    entity_root:  str | Path,
    query:        str,
    gseq_counter: GseqCounter,
    max_results:  int = 5,
) -> list[dict[str, Any]]:
    """Search ``memory/`` for *query* (case-insensitive substring).

    Scans all .md files under memory/ — episodic, semantic, or any other
    subdirectory.  The CPE may recall any memory artifact mid-session;
    recall is a read operation and carries no write authorization requirement.

    MVP implementation: simple substring scan.  Fase 2 will add proper
    semantic search.

    Args:
        entity_root:  Entity root path.
        query:        Search string.
        gseq_counter: MIL's gseq counter for this session.
        max_results:  Maximum number of matching files to return.

    Returns:
        List of ACP envelope dicts written to io/inbox/.
    """
    entity_root = Path(entity_root)
    memory_dir  = entity_root / "memory"

    matches: list[dict[str, str]] = []
    if memory_dir.exists():
        for fp in sorted(memory_dir.rglob("*.md")):
            try:
                text = fp.read_text(encoding="utf-8")
            except OSError:
                continue
            if query.lower() in text.lower():
                matches.append({
                    "path": str(fp.relative_to(entity_root)),
                    "excerpt": text[:500],
                })
            if len(matches) >= max_results:
                break

    result_data = json.dumps({
        "query":   query,
        "count":   len(matches),
        "results": matches,
        "ts":      utcnow_iso(),
    })

    envelopes = chunk_payload(
        actor=ACTOR_MIL,
        type_=TYPE_MEMO_RESULT,
        payload_str=result_data,
        gseq_start=gseq_counter.next(),
    )

    inbox_envelopes: list[dict[str, Any]] = []
    for env in envelopes:
        spool_msg(entity_root, env.to_dict())
        inbox_envelopes.append(env.to_dict())
        if not env.eof:
            gseq_counter._value = env.gseq

    return inbox_envelopes


# ---------------------------------------------------------------------------
# Active context symlinks (§5.1, §8.2)
# ---------------------------------------------------------------------------

def rebuild_active_context(entity_root: str | Path) -> None:
    """Rebuild ``memory/active_context/`` symlinks from working-memory.json.

    Called at Boot Phase 5 (context assembly).  Each entry in the working
    memory pointer map becomes a symlink in active_context/ pointing to the
    actual memory artefact.

    Missing targets are silently skipped (per §5.1 — not a Critical condition).
    """
    entity_root = Path(entity_root)
    ac_dir = entity_root / "memory" / "active_context"
    ac_dir.mkdir(parents=True, exist_ok=True)

    wm_path = entity_root / "memory" / "working-memory.json"
    if not wm_path.exists():
        return

    try:
        wm = read_json(wm_path)
    except Exception:
        return

    entries = wm.get("entries", [])
    # Sort by priority (lower = higher priority)
    entries = sorted(entries, key=lambda e: e.get("priority", 99))

    # Remove stale symlinks first
    for sym in ac_dir.iterdir():
        if sym.is_symlink():
            sym.unlink()

    for entry in entries:
        rel_path = entry.get("path", "")
        target = entity_root / rel_path
        if not target.exists():
            continue  # Drop silently per §5.1
        link_name = ac_dir / target.name
        # Avoid duplicate names from different paths
        counter = 0
        while link_name.exists():
            counter += 1
            link_name = ac_dir / f"{target.stem}_{counter}{target.suffix}"
        link_name.symlink_to(target.resolve())


# ---------------------------------------------------------------------------
# Session Handoff and Working Memory — stubs (Fase 2)
# ---------------------------------------------------------------------------

def read_session_handoff(entity_root: str | Path) -> dict[str, Any] | None:
    """Read session-handoff.json or return None if absent."""
    path = Path(entity_root) / "memory" / "session-handoff.json"
    if not path.exists():
        return None
    try:
        return read_json(path)
    except Exception:
        return None


def write_working_memory(
    entity_root: str | Path,
    entries:     list[dict[str, Any]],
    max_entries: int = 20,
) -> None:
    """Write working-memory.json atomically (Fase 2: called from Sleep Cycle)."""
    entries = entries[:max_entries]
    atomic_write_json(
        Path(entity_root) / "memory" / "working-memory.json",
        {"version": "1.0", "entries": entries},
    )


def write_session_handoff(
    entity_root: str | Path,
    handoff:     dict[str, Any],
) -> None:
    """Write session-handoff.json atomically (Fase 2: called from Sleep Cycle)."""
    atomic_write_json(
        Path(entity_root) / "memory" / "session-handoff.json",
        handoff,
    )


# ---------------------------------------------------------------------------
# Convenience wrappers — used by session loop and boot
# ---------------------------------------------------------------------------

def consolidate_inbox(
    entity_root: str | Path,
    envelopes:   list[dict[str, Any]],
) -> None:
    """Append a list of raw envelope dicts (from drain_inbox) to session.jsonl."""
    path = Path(entity_root) / "memory" / "session.jsonl"
    for env in envelopes:
        append_jsonl(path, env)


def append_session_event(
    entity_root: str | Path,
    event:       dict[str, Any],
) -> None:
    """Append a single event dict directly to session.jsonl."""
    append_jsonl(Path(entity_root) / "memory" / "session.jsonl", event)


def load_active_context(entity_root: str | Path) -> list[dict[str, Any]]:
    """Read content of valid memory/active_context/ symlinks.

    Returns list of {path, content} dicts, sorted by symlink name.
    Broken symlinks are skipped.
    """
    ac_dir = Path(entity_root) / "memory" / "active_context"
    if not ac_dir.exists():
        return []
    entries: list[dict[str, Any]] = []
    for sym in sorted(ac_dir.iterdir()):
        target = sym.resolve() if sym.is_symlink() else sym
        if not target.exists():
            continue
        try:
            entries.append({
                "path":    sym.name,
                "content": target.read_text(encoding="utf-8"),
            })
        except OSError:
            pass
    return entries


def load_session_handoff(entity_root: str | Path) -> dict[str, Any] | None:
    """Alias for read_session_handoff."""
    return read_session_handoff(entity_root)
