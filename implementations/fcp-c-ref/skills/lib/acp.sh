#!/bin/bash
# skills/lib/acp.sh — ACP (Atomic Chunked Protocol) envelope library
#
# Source this file before use:
#   source "$FCP_REF_ROOT/skills/lib/acp.sh"
#
# Provides lockless, crash-safe writes to memory/inbox via spool→rename.
# Every write is an atomic ACP envelope conforming to FCP §4.

# ---------------------------------------------------------------------------
# acp_crc32 <string>
# Returns 8-char lowercase hex CRC-32 of the string (FCP §4).
# ---------------------------------------------------------------------------
acp_crc32() {
    python3 -c "
import zlib, sys
data = sys.argv[1].encode('utf-8')
print(format(zlib.crc32(data) & 0xFFFFFFFF, '08x'))
" "$1"
}

# ---------------------------------------------------------------------------
# acp_new_tx
# Generates a fresh UUID v4 to identify a transaction.
# ---------------------------------------------------------------------------
acp_new_tx() {
    python3 -c "import uuid; print(str(uuid.uuid4()))"
}

# ---------------------------------------------------------------------------
# acp_next_gseq <actor>
# Atomically increments and returns the global sequence counter for <actor>.
# Counter is persisted in state/sentinels/<actor>.gseq
# Uses a lockfile (O_CREAT|O_EXCL semantics via mkdir) to prevent races.
# ---------------------------------------------------------------------------
acp_next_gseq() {
    local actor="$1"
    local sentinel_dir="$FCP_REF_ROOT/state/sentinels"
    local seq_file="${sentinel_dir}/${actor}.gseq"
    local lock_dir="${sentinel_dir}/${actor}.gseq.lock"

    # Spin on lock (max 20 attempts × 50ms = 1s)
    local attempts=0
    while ! mkdir "$lock_dir" 2>/dev/null; do
        attempts=$((attempts + 1))
        if [ $attempts -ge 20 ]; then
            echo "[acp] WARN: gseq lock timeout for actor '${actor}', proceeding without lock" >&2
            break
        fi
        sleep 0.05
    done

    local current=0
    [ -f "$seq_file" ] && current=$(cat "$seq_file" 2>/dev/null || echo 0)
    local next=$((current + 1))
    echo "$next" > "$seq_file"

    rmdir "$lock_dir" 2>/dev/null || true
    echo "$next"
}

# ---------------------------------------------------------------------------
# acp_write <actor> <type> <data> [tx] [seq] [eof]
#
# Writes one ACP envelope to memory/inbox via the spool/rename pattern:
#   1. Write JSON to memory/spool/<actor>/<epoch_ns>-<gseq>.tmp
#   2. fsync (sync)
#   3. Atomic rename → memory/inbox/<epoch_ns>-<gseq>.msg
#
# Arguments:
#   actor  — who is writing (e.g. "el", "sil", "supervisor")
#   type   — ACP type: MSG | SKILL_REQUEST | SKILL_RESULT | SKILL_ERROR |
#             SKILL_TIMEOUT | SCHEDULE | CRON_WAKE | DRIFT_PROBE |
#             DRIFT_FAULT | TRAP | RECOVERY | ROTATION | CTX_ADD | CTX_SKIP
#   data   — payload string (UTF-8; structured payloads must be JSON-serialized)
#   tx     — transaction UUID (optional; generated if omitted)
#   seq    — chunk sequence within tx (default: 1)
#   eof    — "true" if last chunk (default: "true")
#
# Returns the path of the .msg file on success, or exits 1 on failure.
# ---------------------------------------------------------------------------
acp_write() {
    local actor="$1"
    local type="$2"
    local data="$3"
    local tx="${4:-$(acp_new_tx)}"
    local seq="${5:-1}"
    local eof="${6:-true}"

    # Validate 4KB rule
    local data_len=${#data}
    if [ "$data_len" -gt 4000 ]; then
        echo "[acp] ERROR: data exceeds 4000 bytes (${data_len}). Chunk your payload." >&2
        return 1
    fi

    local gseq
    gseq=$(acp_next_gseq "$actor")

    local ts
    ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

    local crc
    crc=$(acp_crc32 "$data")

    local spool_dir="$FCP_REF_ROOT/memory/spool/${actor}"
    local inbox_dir="$FCP_REF_ROOT/memory/inbox"
    mkdir -p "$spool_dir" "$inbox_dir"

    # High-resolution epoch for unique filenames
    local epoch
    epoch=$(python3 -c "import time; print(int(time.time() * 1e9))" 2>/dev/null \
            || date +%s)

    local tmp_file="${spool_dir}/${epoch}-${gseq}.tmp"
    local msg_file="${inbox_dir}/${epoch}-${gseq}.msg"

    # Build envelope
    python3 -c "
import json, sys
a, gseq, tx, seq, eof_s, typ, ts, data, crc = \
    sys.argv[1], int(sys.argv[2]), sys.argv[3], int(sys.argv[4]), \
    sys.argv[5], sys.argv[6], sys.argv[7], sys.argv[8], sys.argv[9]
envelope = {
    'actor': a,
    'gseq':  gseq,
    'tx':    tx,
    'seq':   seq,
    'eof':   (eof_s == 'true'),
    'type':  typ,
    'ts':    ts,
    'data':  data,
    'crc':   crc,
}
print(json.dumps(envelope, ensure_ascii=False))
" "$actor" "$gseq" "$tx" "$seq" "$eof" "$type" "$ts" "$data" "$crc" \
    > "$tmp_file" || { echo "[acp] ERROR: failed to build envelope" >&2; return 1; }

    # fsync before rename — using python3 for target-specific fsync to avoid global sync latency
    python3 -c "import os,sys; fd=os.open(sys.argv[1], os.O_RDONLY); os.fsync(fd); os.close(fd)" "$tmp_file" 2>/dev/null || true

    # Atomic rename into inbox
    mv "$tmp_file" "$msg_file" || { echo "[acp] ERROR: rename failed" >&2; return 1; }

    echo "$msg_file"
}

# ---------------------------------------------------------------------------
# acp_read_inbox
# Reads all .msg files from memory/inbox/ in chronological order (by name).
# Outputs one JSON envelope per line, suitable for piping to jq.
# Does NOT consume (unlink) the files — that is the SIL's responsibility.
# ---------------------------------------------------------------------------
acp_read_inbox() {
    local inbox_dir="$FCP_REF_ROOT/memory/inbox"
    [ -d "$inbox_dir" ] || return 0
    for f in "$inbox_dir"/*.msg; do
        [ -f "$f" ] || continue
        cat "$f"
    done
}

# ---------------------------------------------------------------------------
# acp_read_session [limit]
# Reads the tail of memory/session.jsonl, newest-first.
# Used by skills that need recent session history.
# ---------------------------------------------------------------------------
acp_read_session() {
    local limit="${1:-50}"
    local session_file="$FCP_REF_ROOT/memory/session.jsonl"
    [ -f "$session_file" ] || return 0
    tail -n "$limit" "$session_file" | tac
}
