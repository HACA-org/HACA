"""
MIL — Memory Interface Layer.  §4.2 / FCP §7–8

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
import re
import time
from pathlib import Path
from typing import Any

from .acp import make as acp_encode
from .store import Layout, append_jsonl, atomic_write, read_json, read_jsonl

# Episodic index file: maps slug → [paths] for O(1) memory_recall() lookups
EPISODIC_INDEX_FILE = ".episodic-index.json"

# Session cache file: caches last N turns from session.jsonl for faster boots
SESSION_CACHE_FILE = ".session-cache.json"


# ---------------------------------------------------------------------------
# Index management helpers
# ---------------------------------------------------------------------------

def _read_episodic_index(layout: Layout) -> dict[str, list[str]]:
    """Load episodic index; return empty dict if missing or corrupted."""
    index_file = layout.episodic_dir / EPISODIC_INDEX_FILE
    if not index_file.exists():
        return {}
    try:
        return read_json(index_file)
    except Exception:
        return {}


def _write_episodic_index(layout: Layout, index: dict[str, list[str]]) -> None:
    """Save episodic index to disk."""
    layout.episodic_dir.mkdir(parents=True, exist_ok=True)
    index_file = layout.episodic_dir / EPISODIC_INDEX_FILE
    atomic_write(index_file, index)


def _rebuild_episodic_index(layout: Layout) -> dict[str, list[str]]:
    """Rebuild episodic index from filesystem (recovery operation).

    Called when index is corrupted or missing; scans episodic_dir and rebuilds
    slug→[paths] mapping. Used during boot or maintenance.
    """
    index: dict[str, list[str]] = {}
    if not layout.episodic_dir.exists():
        return index
    for f in sorted(layout.episodic_dir.glob("*-*.md")):
        # Extract slug from <timestamp>-<slug>.md
        match = re.search(r"-([^-]+)\.md$", f.name)
        if match:
            slug = match.group(1)
            rel = str(f.relative_to(layout.root))
            if slug not in index:
                index[slug] = []
            index[slug].append(rel)
    _write_episodic_index(layout, index)
    return index


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

    Maintains episodic index for O(1) slug lookups.
    Returns the Path written on success.
    """
    # Sanitize slug: keep only alphanumerics, hyphens, underscores, and dots.
    # Prevents glob wildcard injection and path traversal.
    slug = re.sub(r"[^\w\-.]", "-", slug)

    existing = sorted(
        layout.episodic_dir.glob(f"*-{slug}.md"),
        key=lambda p: p.name,
        reverse=True,
    )
    if existing and not overwrite:
        current = existing[0].read_text(encoding="utf-8")
        return {"conflict": slug, "existing_content": current}

    # Load index and remove old entries for this slug
    index = _read_episodic_index(layout)
    if overwrite and slug in index:
        # Delete all old files listed in index
        for rel in index.get(slug, []):
            f = layout.root / rel
            if f.exists():
                f.unlink()
        # Clear index entry for this slug
        index[slug] = []

    # Also delete any existing files found by glob (in case index is out of sync)
    for f in existing:
        if f.exists():
            f.unlink()

    ts = int(time.time() * 1000)
    dest = layout.episodic_dir / f"{ts}-{slug}.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding="utf-8")

    # Update index
    rel = str(dest.relative_to(layout.root))
    if slug not in index:
        index[slug] = []
    if rel not in index[slug]:
        index[slug].append(rel)
    _write_episodic_index(layout, index)

    return dest


def write_semantic(layout: Layout, key: str, content: str) -> Path:
    """Write *content* directly to memory/semantic/<key>.md.

    Used during Stage 3 (Endure) and by the SIL when integrating
    Operator-approved semantic content without a prior episodic file.
    """
    dest = layout.semantic_dir / f"{key}.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding="utf-8")
    return dest


def promote_to_semantic(layout: Layout, slug: str) -> bool:
    """Integrate an episodic slug into memory/semantic/<slug>.md (Stage 3).

    Uses episodic index for O(1) lookup; if index is missing, falls back to
    filesystem scan and rebuilds index.  Called by the SIL during Stage 3
    execution of an authorized memory promotion proposal.

    Returns True if the slug was found and promoted, False if not found.
    """
    # Try index first
    index = _read_episodic_index(layout)
    if slug not in index or not index[slug]:
        # Index miss — rebuild and retry
        index = _rebuild_episodic_index(layout)
        if slug not in index or not index[slug]:
            return False

    # Get most recent file for this slug
    paths = sorted(index[slug], reverse=True)
    source = layout.root / paths[0]

    if not source.exists():
        return False

    content = source.read_text(encoding="utf-8")
    dest = layout.semantic_dir / f"{slug}.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
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
    of *path*.  Uses episodic index for O(1) slug resolution.
    Returns the result dict (also written synchronously to inbox).
    """
    paths: list[str] = []
    status = "not_found"

    if path:
        target = layout.root / path
        # If the path doesn't exist directly, try to resolve it as a slug using index
        if not target.exists() or target == layout.root:
            slug = Path(path).name
            slug = re.sub(r"[^\w\-.]", "-", slug)
            index = _read_episodic_index(layout)

            # Try index lookup first
            if slug in index and index[slug]:
                # Get most recent file
                most_recent = sorted(index[slug], reverse=True)[0]
                target = layout.root / most_recent
                path = most_recent
            else:
                # Index miss — rebuild and retry
                index = _rebuild_episodic_index(layout)
                if slug in index and index[slug]:
                    most_recent = sorted(index[slug], reverse=True)[0]
                    target = layout.root / most_recent
                    path = most_recent

        if target.exists() and target != layout.root:
            status = "found"
            paths = [path]
            link_name = Path(path).name
            link = layout.active_context_dir / link_name
            if link.is_symlink():
                link.unlink()
                link.symlink_to(target.resolve())
            elif link.exists():
                pass  # directory or regular file collision — skip symlink creation
            else:
                link.symlink_to(target.resolve())
    else:
        # query-only recall: search episodic and semantic memory by filename and content
        q = query.lower()
        candidates: list[Path] = []
        for search_dir in (layout.episodic_dir, layout.semantic_dir):
            if search_dir.exists():
                candidates.extend(sorted(search_dir.rglob("*.md")))
                candidates.extend(sorted(search_dir.rglob("*.jsonl")))
        for f in candidates:
            name_match = not q or q in f.name.lower()
            if not name_match:
                try:
                    name_match = q in f.read_text(encoding="utf-8").lower()
                except Exception:
                    pass
            if not name_match:
                continue
            rel = str(f.relative_to(layout.root))
            paths.append(rel)
            link = layout.active_context_dir / f.name
            if link.is_symlink():
                link.unlink()
            if not link.exists():
                link.symlink_to(f.resolve())
        status = "found" if paths else "not_found"

    # Include file contents so the CPE can read the recalled memory directly.
    contents: list[dict[str, Any]] = []
    for rel in paths:
        p = layout.root / rel
        try:
            contents.append({"path": rel, "content": p.read_text(encoding="utf-8")})
        except Exception:
            contents.append({"path": rel, "content": ""})

    return {
        "query": query,
        "paths": paths,
        "contents": contents,
        "status": status,
    }


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
        if link.is_symlink():
            link.unlink()
        elif link.is_dir():
            continue  # directory collision — skip
        elif link.exists():
            link.unlink()
        link.symlink_to(target.resolve())

    return skipped


# ---------------------------------------------------------------------------
# Stage 2 — remove stale symlinks
# ---------------------------------------------------------------------------

def clean_stale_symlinks(layout: Layout) -> None:
    """Remove broken symlinks from memory/active_context/ (Stage 2).

    Cleans both:
    1. Broken symlinks (targets no longer exist)
    2. Orphaned symlinks (not in working_memory, not recently accessed)

    This prevents unbounded accumulation of stale context symlinks.
    """
    if not layout.active_context_dir.exists():
        return

    # Get list of paths in working_memory (these should be kept)
    allowed_paths: set[str] = set()
    if layout.working_memory.exists():
        try:
            wm = read_json(layout.working_memory)
            for entry in wm.get("entries", []):
                path = entry.get("path", "")
                if path:
                    # Store just the basename for matching with symlink names
                    allowed_paths.add(Path(path).name)
        except Exception:
            pass

    # Clean symlinks
    for link in layout.active_context_dir.iterdir():
        # Always remove broken symlinks
        if link.is_symlink() and not link.exists():
            link.unlink()
        # Remove symlinks not in working_memory (unless they're recent session artifacts)
        elif link.is_symlink():
            # Keep symlink if its name appears in working_memory paths
            if allowed_paths and link.name not in allowed_paths:
                # Symlink not in working_memory; remove it
                # This prevents accumulation while respecting current context
                link.unlink()


def clean_episodic_index(layout: Layout) -> None:
    """Remove orphaned entries from episodic index (Stage 2).

    Scans index and removes slug entries where all files are missing from disk.
    Rebuilds index if corruption detected.
    """
    index = _read_episodic_index(layout)
    if not index:
        return

    cleaned: dict[str, list[str]] = {}
    for slug, paths in index.items():
        valid = [p for p in paths if (layout.root / p).exists()]
        if valid:
            cleaned[slug] = valid

    if cleaned != index:
        _write_episodic_index(layout, cleaned)


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
        if not rel:
            continue
        valid.append(entry)
        # Paths that don't exist yet (e.g. session-handoff written below) are kept.
        # Stale paths will be dropped at seed_active_context time.

    valid_sorted = sorted(valid, key=lambda e: int(e.get("priority", 99)))
    if len(valid_sorted) > max_entries:
        valid_sorted = list(itertools.islice(valid_sorted, max_entries))

    atomic_write(layout.working_memory, {"entries": valid_sorted})

    # 3. session-handoff
    session_handoff = payload.get("session_handoff", {})
    if not isinstance(session_handoff, dict):
        session_handoff = {}
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
# Session cache — speed up boot by caching last N turns
# ---------------------------------------------------------------------------

def cache_session_tail(layout: Layout, max_turns: int = 100) -> None:
    """Cache last N turns from session.jsonl for faster boot (Stage 3 end).

    Called after sleep Stage 3 to cache the session tail, avoiding full
    session.jsonl scan on next boot. If session is empty, cache is cleared.
    """
    from .session import _session_to_turns

    cache_file = layout.root / "memory" / SESSION_CACHE_FILE
    cache_file.parent.mkdir(parents=True, exist_ok=True)

    try:
        pairs = _session_to_turns(layout)
        # Keep only last max_turns to bound cache size
        if len(pairs) > max_turns:
            pairs = pairs[-max_turns:]

        # Convert to list of dicts for JSON serialization
        turns = [{"role": role, "content": content} for role, content in pairs]
        cache_data = {"turns": turns, "cached_at": int(time.time())}
        atomic_write(cache_file, cache_data)
    except Exception:
        # If caching fails, remove cache to force full scan on next boot
        if cache_file.exists():
            cache_file.unlink()


def clear_session_cache(layout: Layout) -> None:
    """Clear session cache to force full session scan on next boot."""
    cache_file = layout.root / "memory" / SESSION_CACHE_FILE
    if cache_file.exists():
        cache_file.unlink()


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

