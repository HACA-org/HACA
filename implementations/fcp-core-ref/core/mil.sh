#!/bin/bash
# core/mil.sh — Memory Interface Layer (HACA-Arch §4.2)
# Exclusive write authority over mnemonic content (Session and Memory Store).

set -euo pipefail

# ---------------------------------------------------------------------------
# Initial environment check
# ---------------------------------------------------------------------------
if [ -z "${FCP_REF_ROOT:-}" ]; then
    echo "[MIL] ERROR: FCP_REF_ROOT not set" >&2
    exit 1
fi

# Load ACP library
source "$FCP_REF_ROOT/skills/lib/acp.sh"

SESSION_FILE="$FCP_REF_ROOT/memory/session.jsonl"
AGENDA_FILE="$FCP_REF_ROOT/state/agenda.jsonl"
EPISODIC_DIR="$FCP_REF_ROOT/memory/episodic"
SEMANTIC_DIR="$FCP_REF_ROOT/memory/semantic"

# ---------------------------------------------------------------------------
# mil_drain_inbox
# Consolidates inbox/*.msg → session.jsonl or agenda.jsonl.
# ---------------------------------------------------------------------------
mil_drain_inbox() {
    local inbox="$FCP_REF_ROOT/memory/inbox"
    mkdir -p "$inbox"

    local count_session=0
    local count_agenda=0

    # Ensure files are processed in chronological order
    for msg in $(ls "$inbox"/*.msg 2>/dev/null | sort); do
        [ -f "$msg" ] || continue

        local env_type
        env_type=$(python3 -c "import json, sys; print(json.loads(open(sys.argv[1]).read()).get('type',''))" "$msg" 2>/dev/null || echo "UNKNOWN")

        if [ "$env_type" = "SCHEDULE" ]; then
            cat "$msg" >> "$AGENDA_FILE"
            count_agenda=$((count_agenda + 1))
        else
            cat "$msg" >> "$SESSION_FILE"
            count_session=$((count_session + 1))
        fi
        rm -f "$msg"
    done

    [ "$count_session" -gt 0 ] && echo "[MIL] DRAIN: ${count_session} msgs → session.jsonl" >&2
    [ "$count_agenda" -gt 0 ]  && echo "[MIL] DRAIN: ${count_agenda} msgs → agenda.jsonl" >&2
}

# ---------------------------------------------------------------------------
# mil_consolidate
# Moves session data to long-term memory (Episodic/Semantic).
# Running during Sleep Cycle.
# ---------------------------------------------------------------------------
mil_consolidate() {
    echo "[MIL] Starting memory consolidation..." >&2
    
    if [ ! -f "$SESSION_FILE" ] || [ ! -s "$SESSION_FILE" ]; then
        echo "[MIL] No session data to consolidate." >&2
        return 0
    fi

    # Create a unique episodic fragment for this session
    local ts
    ts=$(date -u +"%Y-%m-%dT%H%M%SZ")
    local fragment_file="${EPISODIC_DIR}/session_${ts}.jsonl"
    
    mkdir -p "$EPISODIC_DIR"
    
    # Simple consolidation: move session to episodic
    mv "$SESSION_FILE" "$fragment_file"
    touch "$SESSION_FILE"
    
    echo "[MIL] Session consolidated to ${fragment_file}" >&2
}

# ---------------------------------------------------------------------------
# mil_read_context [budget]
# Assembles the session tail context for the CPE.
# ---------------------------------------------------------------------------
mil_read_context() {
    local budget="${1:-60000}"
    if [ -f "$SESSION_FILE" ]; then
        # Tail newest-first up to budget
        python3 -c "
import json, os, sys
session_path = '$SESSION_FILE'
budget = int(sys.argv[1])
if not os.path.exists(session_path):
    sys.exit(0)
lines = []
with open(session_path, 'r', errors='replace') as f:
    for line in f:
        line = line.rstrip('\n')
        if line: lines.append(line)
lines.reverse()
used = 0
for line in lines:
    if used + len(line) + 1 > budget: break
    print(line)
    used += len(line) + 1
" "$budget"
    fi
}

# CLI entry point
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    case "${1:-}" in
        drain) mil_drain_inbox ;;
        consolidate) mil_consolidate ;;
        context) mil_read_context "${2:-60000}" ;;
        *) echo "Usage: $0 {drain|consolidate|context}" >&2; exit 1 ;;
    esac
fi
