#!/bin/bash
# skills/lib/rotation.sh — Crash-safe session.jsonl log rotation (FCP §11)
#
# Source this file before use:
#   source "$FCP_REF_ROOT/skills/lib/rotation.sh"
#
# Uses write-ahead logging (rotation.journal) + atomic rename.
# Safe to call from multiple processes — uses mkdir-based lock.

# ---------------------------------------------------------------------------
# rotation_recover
# Called during Phase 1 (crash recovery). Completes any interrupted rotation
# found in state/rotation.journal.
# ---------------------------------------------------------------------------
rotation_recover() {
    local journal="$FCP_REF_ROOT/state/rotation.journal"
    [ -f "$journal" ] || return 0

    echo "[rotation] Found interrupted rotation. Recovering..." >&2

    # Read the journal: one JSON object
    # Fields: src, dst, new_src, ts
    local src dst new_src
    src=$(python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(d['src'])" "$journal" 2>/dev/null)
    dst=$(python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(d['dst'])" "$journal" 2>/dev/null)
    new_src=$(python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(d['new_src'])" "$journal" 2>/dev/null)

    if [ -z "$src" ] || [ -z "$dst" ]; then
        echo "[rotation] WARN: malformed journal, removing." >&2
        rm -f "$journal"
        return 0
    fi

    # If src still exists and dst does not → rename was never done
    if [ -f "$src" ] && [ ! -f "$dst" ]; then
        local dst_dir
        dst_dir=$(dirname "$dst")
        mkdir -p "$dst_dir"
        mv "$src" "$dst"
        echo "[rotation] Recovered: renamed $src → $dst" >&2
    fi

    # If new_src doesn't exist → create it
    if [ ! -f "$new_src" ]; then
        touch "$new_src"
        echo "[rotation] Recovered: created new session file $new_src" >&2
    fi

    # Remove the journal entry (rotation complete)
    rm -f "$journal"
    echo "[rotation] Recovery complete." >&2
}

# ---------------------------------------------------------------------------
# rotation_maybe <size_limit_bytes>
# Rotates session.jsonl if it exceeds the size limit.
# Default limit: 2MB (2097152 bytes).
#
# Rotation sequence (FCP §11):
#   1. Acquire rotation.lock (mkdir atomic)
#   2. Write intent to rotation.journal (fsync)
#   3. Atomic rename: session.jsonl → archive/YYYY-MM/session-<ts>.jsonl
#   4. Create new empty session.jsonl
#   5. Delete rotation.journal
#   6. Remove rotation.lock
# ---------------------------------------------------------------------------
rotation_maybe() {
    # Limit: arg > ROTATION_LIMIT env var > default 2MB (RFC §11 default)
    local limit="${1:-${ROTATION_LIMIT:-2097152}}"
    local session="$FCP_REF_ROOT/memory/session.jsonl"
    local lock_dir="$FCP_REF_ROOT/state/rotation.lock"
    local journal="$FCP_REF_ROOT/state/rotation.journal"

    # Skip if session doesn't exist or is within limit
    [ -f "$session" ] || return 0
    local size
    size=$(wc -c < "$session" 2>/dev/null || echo 0)
    [ "$size" -lt "$limit" ] && return 0

    echo "[rotation] session.jsonl is ${size} bytes (limit ${limit}). Rotating..." >&2

    # Step 1: Acquire lock
    local attempts=0
    while ! mkdir "$lock_dir" 2>/dev/null; do
        attempts=$((attempts + 1))
        if [ $attempts -ge 30 ]; then
            echo "[rotation] WARN: could not acquire rotation.lock after 3s. Skipping." >&2
            return 1
        fi
        sleep 0.1
    done

    # Determine archive path
    local year_month
    year_month=$(date -u +"%Y-%m")
    local ts
    ts=$(date -u +"%Y%m%dT%H%M%SZ")
    local archive_dir="$FCP_REF_ROOT/memory/archive/${year_month}"
    local archive_file="${archive_dir}/session-${ts}.jsonl"

    mkdir -p "$archive_dir"

    # Step 2: Write intent to journal (crash recovery anchor)
    python3 -c "
import json
journal = {
    'src':     '$session',
    'dst':     '$archive_file',
    'new_src': '$session',
    'ts':      '$(date -u +"%Y-%m-%dT%H:%M:%SZ")',
}
print(json.dumps(journal))
" > "$journal"
    # fsync journal before moving on — using python3 for target-specific fsync
    python3 -c "import os,sys; fd=os.open(sys.argv[1], os.O_RDONLY); os.fsync(fd); os.close(fd)" "$journal" 2>/dev/null || true

    # Step 3: Atomic rename
    mv "$session" "$archive_file"

    # Step 4: Create new empty session.jsonl
    touch "$session"

    # Step 5: Remove journal
    rm -f "$journal"

    # Step 6: Release lock
    rmdir "$lock_dir" 2>/dev/null || true

    echo "[rotation] Rotated → ${archive_file}" >&2
}
