"""
MIL — Memory Interface Layer.  §4.2 / FCP-Core §7–8

Exclusive write authority over mnemonic content (memory/ directory).
Does not interpret or evaluate stored data — reads and writes on request.

Memory Store layout:
  memory/episodic/  — session notes written mid-session via memory_write (slug-keyed)
                      also receives session.jsonl rotations (SIL, Stage 2)
  memory/semantic/  — crystallized knowledge base; written by MIL at Stage 3
                      only after Operator-approved Evolution Proposal
  memory/active_context/ — symlinks; seeded at boot Phase 5, extended by memory_recall

Sleep Cycle responsibilities:
  Stage 1 (MIL): read pending-closure.json → consolidation MSG, working-memory,
                 session-handoff; delete file.  promotion[] is extracted by FCP
                 before Stage 1 and queued as an Evolution Proposal for Stage 3.
  Stage 2 (SIL): session.jsonl rotation; MIL cleans stale symlinks.
  Stage 3 (SIL): on authorized promotion — SIL triggers MIL to integrate slugs
                 from episodic/ into semantic/; MIL appends ENDURE_COMMIT.
"""

from __future__ import annotations

import itertools
import json
import os
import time
from pathlib import Path
from typing import Any

from .acp import make as acp_encode
from .store import Layout, append_jsonl, atomic_write, read_json, read_jsonl


# ---------------------------------------------------------------------------
# Mid-session writes
# ---------------------------------------------------------------------------

def write_episodic(
    layout: Layout, slug: str, content: str, overwrite: bool = False
) -> Path | dict[str, str]:
    """Write CPE memory_write content to memory/episodic/<timestamp>-<slug>.md.

    If a file with the same slug already exists and overwrite is False, returns
    a dict {"conflict": slug, "existing_content": <str>} instead of writing.
    If overwrite is True, deletes all existing files for this slug before writing.

    Returns the Path written on success.
    """
    existing = sorted(
        layout.episodic_dir.glob(f"*-{slug}.md"),
        key=lambda p: p.name,
        reverse=True,
    )
    if existing and not overwrite:
        current = existing[0].read_text(encoding="utf-8")
        return {"conflict": slug, "existing_content": current}
    for f in existing:
        f.unlink()
    ts = int(time.time() * 1000)
    dest = layout.episodic_dir / f"{ts}-{slug}.md"
    dest.write_text(content, encoding="utf-8")
    return dest


def write_semantic(layout: Layout, key: str, content: str) -> Path:
    """Write *content* directly to memory/semantic/<key>.md.

    Used during Stage 3 (Endure) and by the SIL when integrating
    Operator-approved semantic content without a prior episodic file.
    """
    dest = layout.semantic_dir / f"{key}.md"
    dest.write_text(content, encoding="utf-8")
    return dest


def promote_to_semantic(layout: Layout, slug: str) -> bool:
    """Integrate an episodic slug into memory/semantic/<slug>.md (Stage 3).

    Finds the most recent episodic file matching *slug*, writes its content
    to semantic/.  Called by the SIL during Stage 3 execution of an
    authorized memory promotion proposal.

    Returns True if the slug was found and promoted, False if not found.
    """
    matches = sorted(
        layout.episodic_dir.glob(f"*-{slug}.md"),
        key=lambda p: p.name,
        reverse=True,
    )
    if not matches:
        return False
    source = matches[0]
    content = source.read_text(encoding="utf-8")
    dest = layout.semantic_dir / f"{slug}.md"
    tmp = dest.with_suffix(".md.tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, dest)
    return True


# ---------------------------------------------------------------------------
# Memory recall
# ---------------------------------------------------------------------------

def memory_recall(layout: Layout, query: str, path: str) -> dict[str, Any]:
    """Process a memory_recall action from the CPE.

    Creates/replaces a symlink in active_context/ named after the basename
    of *path*.  Writes a MEMORY_RESULT ACP envelope to io/inbox/.
    Returns the result dict (also written synchronously to inbox).
    """
    paths: list[str] = []
    status = "not_found"

    if path:
        target = layout.root / path
        if target.exists() and target != layout.root:
            status = "found"
            paths = [path]
            link_name = Path(path).name
            link = layout.active_context_dir / link_name
            if link.is_symlink():
                link.unlink()
            elif link.exists():
                pass  # directory or regular file collision — skip symlink creation
            else:
                link.symlink_to(target)
    else:
        # query-only recall: search episodic memory for matching files
        ep_dir = layout.episodic_dir
        if ep_dir.exists():
            q = query.lower()
            for f in sorted(ep_dir.rglob("*.md")) + sorted(ep_dir.rglob("*.jsonl")):
                if q and q not in f.name.lower():
                    continue
                rel = str(f.relative_to(layout.root))
                paths.append(rel)
                link = layout.active_context_dir / f.name
                if link.is_symlink():
                    link.unlink()
                if not link.exists():
                    link.symlink_to(f)
        status = "found" if paths else "not_found"

    # Include file contents so the CPE can read the recalled memory directly.
    contents: list[dict[str, Any]] = []
    for rel in paths:
        p = layout.root / rel
        try:
            contents.append({"path": rel, "content": p.read_text(encoding="utf-8")})
        except Exception:
            contents.append({"path": rel, "content": ""})

    result_data: dict[str, Any] = {
        "query": query,
        "paths": paths,
        "contents": contents,
        "status": status,
    }
    envelope = acp_encode(
        env_type="MEMORY_RESULT",
        source="mil",
        data=result_data,
    )
    _write_inbox(layout, envelope)
    return result_data


# ---------------------------------------------------------------------------
# Result recall — retrieve full tool result payload by timestamp
# ---------------------------------------------------------------------------

def result_recall(layout: Layout, ts: int) -> dict[str, Any]:
    """Return the full tool result payload stored in session.jsonl for the given ts.

    Matches by the numeric _ts_ms field embedded in the tool_result content,
    which is set by session._return_tool_result().
    """
    for env in read_jsonl(layout.session_store):
        raw = env.get("data", {})
        if isinstance(raw, str):
            try:
                data = json.loads(raw)
            except Exception:
                continue
        else:
            data = raw
        if not isinstance(data, dict):
            continue
        tr = data.get("tool_result", {})
        content = tr.get("content", {})
        if isinstance(content, dict) and int(content.get("_ts_ms", -1)) == ts:
            # return payload without the internal _ts_ms marker
            payload = {k: v for k, v in tr.items()}
            payload["content"] = {k: v for k, v in content.items() if k != "_ts_ms"}
            return {"ts": ts, "status": "found", "payload": payload}
    return {"ts": ts, "status": "not_found"}


# ---------------------------------------------------------------------------
# Read active context (on-demand, during session)
# ---------------------------------------------------------------------------

def read_active_context(layout: Layout) -> list[str]:
    """Return contents of all valid symlinks in active_context/, sorted by name."""
    if not layout.active_context_dir.exists():
        return []
    entries: list[str] = []
    for link in sorted(layout.active_context_dir.iterdir()):
        if link.is_symlink() and link.exists():
            entries.append(link.read_text(encoding="utf-8"))
    return entries


# ---------------------------------------------------------------------------
# Boot Phase 5 — seed active_context/ from working-memory.json
# ---------------------------------------------------------------------------

def seed_active_context(layout: Layout) -> list[str]:
    """Build active_context/ symlinks from working-memory.json.

    Returns list of paths dropped (absent artefacts); caller logs each as
    a CTX_SKIP to state/integrity.log.
    """
    if not layout.working_memory.exists():
        return []

    wm = read_json(layout.working_memory)
    entries: list[dict[str, Any]] = wm.get("entries", [])
    entries_sorted = sorted(entries, key=lambda e: int(e.get("priority", 99)))

    skipped: list[str] = []
    for entry in entries_sorted:
        rel = entry.get("path", "")
        target = layout.root / rel
        if not target.exists():
            skipped.append(rel)
            continue
        link_name = Path(rel).name
        link = layout.active_context_dir / link_name
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(target)

    return skipped


# ---------------------------------------------------------------------------
# Stage 2 — remove stale symlinks
# ---------------------------------------------------------------------------

def clean_stale_symlinks(layout: Layout) -> None:
    """Remove broken symlinks from memory/active_context/."""
    if not layout.active_context_dir.exists():
        return
    for link in layout.active_context_dir.iterdir():
        if link.is_symlink() and not link.exists():
            link.unlink()


# ---------------------------------------------------------------------------
# Sleep Cycle Stage 1 — process Closure Payload
# ---------------------------------------------------------------------------

def process_closure(layout: Layout) -> bool:
    """Read and process state/pending-closure.json (Stage 1).

    Returns True if processed, False if absent (forced close — Stage 1 no-op).

    The `promotion` array is extracted by FCP before calling this function
    and queued as an Evolution Proposal for Stage 3.  Stage 1 does not touch
    memory/semantic/.

    Processing order:
      1. Append consolidation string to session.jsonl as MSG envelope.
      2. Validate working_memory paths, enforce max_entries, write file.
      3. Write session-handoff.json (replacing previous).
      4. Delete pending-closure.json.
    """
    if not layout.pending_closure.exists():
        return False

    payload = read_json(layout.pending_closure)

    # 1. consolidation → MSG in session.jsonl
    consolidation = payload.get("consolidation", "")
    if consolidation:
        envelope = acp_encode(
            env_type="MSG",
            source="mil",
            data=consolidation,
        )
        append_jsonl(layout.session_store, envelope)

    # 2. working_memory → validate, enforce limit, write
    wm_entries: list[dict[str, Any]] = payload.get("working_memory", [])
    max_entries = _working_memory_max(layout)
    valid: list[dict[str, Any]] = []
    for entry in wm_entries:
        # CPE may send strings instead of {priority, path} dicts — normalize
        if isinstance(entry, str):
            entry = {"priority": 99, "path": entry}
        if not isinstance(entry, dict):
            continue
        rel = entry.get("path", "")
        if (layout.root / rel).exists():
            valid.append(entry)
        # invalid paths: caller (SIL) must log CTX_SKIP to integrity.log

    valid_sorted = sorted(valid, key=lambda e: int(e.get("priority", 99)))
    if len(valid_sorted) > max_entries:
        valid_sorted = list(itertools.islice(valid_sorted, max_entries))

    atomic_write(layout.working_memory, {"entries": valid_sorted})

    # 3. session-handoff
    session_handoff: dict[str, Any] = payload.get("session_handoff", {})
    atomic_write(layout.session_handoff, session_handoff)

    # 4. delete pending-closure.json
    layout.pending_closure.unlink()

    return True


# ---------------------------------------------------------------------------
# Mid-session Session Summarization (Degraded corrective action)
# ---------------------------------------------------------------------------

def summarize_session(layout: Layout) -> None:
    """Rewrite session.jsonl retaining the newest 50% of bytes.

    Prepends a boundary MSG envelope with data "session summarized".
    Called synchronously by the SIL when session store approaches
    session_store.rotation_threshold_bytes.
    """
    if not layout.session_store.exists():
        return

    raw = layout.session_store.read_bytes()
    if not raw:
        return

    keep_start = len(raw) // 2
    newline_pos = raw.find(b"\n", keep_start)
    if newline_pos == -1:
        kept = raw
    else:
        kept = raw[newline_pos + 1:]

    marker = acp_encode(env_type="MSG", source="mil", data="session summarized")
    marker_line = (json.dumps(marker, separators=(",", ":")) + "\n").encode()

    tmp = layout.session_store.with_suffix(".jsonl.tmp")
    tmp.write_bytes(marker_line + kept)
    os.replace(tmp, layout.session_store)


# ---------------------------------------------------------------------------
# Stage 3 support — ENDURE_COMMIT append
# ---------------------------------------------------------------------------

def append_endure_commit(layout: Layout, seq: int, files: dict[str, str]) -> None:
    """Append an ENDURE_COMMIT ACP envelope to session.jsonl.

    Called by the SIL during Stage 3 Step 6.  MIL remains the authoritative
    writer of session.jsonl even during Endure execution.
    """
    envelope = acp_encode(
        env_type="ENDURE_COMMIT",
        source="sil",
        data={"seq": seq, "files": files},
    )
    append_jsonl(layout.session_store, envelope)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _working_memory_max(layout: Layout) -> int:
    """Read working_memory.max_entries from baseline; default 50."""
    try:
        baseline = read_json(layout.baseline)
        wm = baseline.get("working_memory", {})
        val = wm.get("max_entries", 50)
        return int(val)
    except (FileNotFoundError, KeyError, ValueError):
        return 50


def _write_inbox(layout: Layout, envelope: dict[str, Any]) -> None:
    """Write a single ACP envelope as a timestamped .json file to io/inbox/."""
    ts = int(time.time() * 1000)
    env_type = str(envelope.get("type", "msg")).lower()
    dest = layout.inbox_dir / f"{ts}_{env_type}.json"
    tmp = dest.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(envelope, indent=2), encoding="utf-8")
    os.replace(tmp, dest)
