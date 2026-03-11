#!/bin/bash
# core/mil.sh — Memory Interface Layer (HACA-Arch §4.2)
# Exclusive write authority over mnemonic content (Session and Memory Store).
#
# Commands:
#   drain    — consolidate inbox/*.msg → session.jsonl / agenda.jsonl
#   stage1   — Sleep Cycle Stage 1: Memory Consolidation
#   stage2   — Sleep Cycle Stage 2: Garbage Collection
#   context  — assemble session tail context for CPE

set -euo pipefail

if [ -z "${FCP_REF_ROOT:-}" ]; then
    echo "[MIL] ERROR: FCP_REF_ROOT not set" >&2
    exit 1
fi

source "$FCP_REF_ROOT/skills/lib/acp.sh"

SESSION_FILE="$FCP_REF_ROOT/memory/session.jsonl"
AGENDA_FILE="$FCP_REF_ROOT/state/agenda.jsonl"
EPISODIC_DIR="$FCP_REF_ROOT/memory/episodic"
ACTIVE_CTX_DIR="$FCP_REF_ROOT/memory/active_context"
WORKING_MEMORY="$FCP_REF_ROOT/memory/working-memory.json"
SESSION_HANDOFF="$FCP_REF_ROOT/memory/session-handoff.json"
PRESESSION_DIR="$FCP_REF_ROOT/memory/inbox/presession"
SPOOL_DIR="$FCP_REF_ROOT/memory/spool"

# ---------------------------------------------------------------------------
# mil_drain_inbox
# Consolidates inbox/*.msg → session.jsonl or agenda.jsonl.
# Pre-session buffer (inbox/presession/) is injected first.
# ---------------------------------------------------------------------------
mil_drain_inbox() {
    local inbox="$FCP_REF_ROOT/memory/inbox"
    mkdir -p "$inbox"
    mkdir -p "$PRESESSION_DIR"

    local count_session=0
    local count_agenda=0

    # Inject pre-session buffer first (FIFO order)
    for msg in $(ls "$PRESESSION_DIR"/*.msg 2>/dev/null | sort); do
        [ -f "$msg" ] || continue
        cat "$msg" >> "$SESSION_FILE"
        rm -f "$msg"
        count_session=$((count_session + 1))
    done

    # Drain main inbox
    for msg in $(ls "$inbox"/*.msg 2>/dev/null | sort); do
        [ -f "$msg" ] || continue

        local env_type
        env_type=$(python3 -c \
            "import json,sys; print(json.loads(open(sys.argv[1]).read()).get('type',''))" \
            "$msg" 2>/dev/null || echo "UNKNOWN")

        if [ "$env_type" = "SCHEDULE" ]; then
            cat "$msg" >> "$AGENDA_FILE"
            count_agenda=$((count_agenda + 1))
        else
            cat "$msg" >> "$SESSION_FILE"
            count_session=$((count_session + 1))
        fi
        rm -f "$msg"
    done

    [ "$count_session" -gt 0 ] && echo "[MIL] DRAIN: ${count_session} msgs → session.jsonl" >&2 || true
    [ "$count_agenda" -gt 0 ]  && echo "[MIL] DRAIN: ${count_agenda} msgs → agenda.jsonl" >&2 || true
}

# ---------------------------------------------------------------------------
# mil_stage1_consolidate
# Sleep Cycle Stage 1 — Memory Consolidation.
#
# Collects the Closure Payload from CPE output already written to session.jsonl,
# archives session to episodic store, and writes:
#   memory/working-memory.json  — pointer map for next session
#   memory/session-handoff.json — pending tasks / next steps
#
# Full Closure Payload (consolidation_content, working_memory declaration,
# session_handoff) is produced by CPE in step 2. For now, this stage
# archives the session and creates placeholder artefacts so the boot
# sequence can load them.
# ---------------------------------------------------------------------------
mil_stage1_consolidate() {
    echo "[MIL] Stage 1: Memory Consolidation..." >&2

    mkdir -p "$EPISODIC_DIR"
    mkdir -p "$(dirname "$WORKING_MEMORY")"

    # Drain inbox one final time to capture Closure Payload
    mil_drain_inbox

    if [ ! -f "$SESSION_FILE" ] || [ ! -s "$SESSION_FILE" ]; then
        echo "[MIL] Stage 1: No session data to archive." >&2
    else
        local ts
        ts=$(date -u +"%Y-%m-%dT%H%M%SZ")
        local fragment="${EPISODIC_DIR}/session_${ts}.jsonl"
        cp "$SESSION_FILE" "$fragment"
        : > "$SESSION_FILE"   # truncate, do not delete (avoids race)
        echo "[MIL] Stage 1: Session archived → ${fragment}" >&2

        # Extract Closure Payload if CPE wrote one
        # CPE marks its closure block with type=CLOSURE_PAYLOAD
        mil_apply_closure_payload "$fragment"

        # Register episodic fragment in Working Memory if not already there
        mil_update_working_memory "$fragment"
    fi

    # Write Session Handoff placeholder if none exists
    if [ ! -f "$SESSION_HANDOFF" ]; then
        local ts
        ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
        python3 - <<PYEOF
import json, os

handoff = {
    "version": "1.0",
    "updated_at": "$ts",
    "pending_tasks": [],
    "next_steps": [],
    "notes": "No explicit session handoff from CPE."
}
tmp = "$SESSION_HANDOFF" + ".tmp"
with open(tmp, "w") as f:
    json.dump(handoff, f, indent=2)
os.replace(tmp, "$SESSION_HANDOFF")
PYEOF
        echo "[MIL] Stage 1: Placeholder Session Handoff written." >&2
    fi

    echo "[MIL] Stage 1: Memory Consolidation complete." >&2
}

# ---------------------------------------------------------------------------
# mil_apply_closure_payload <fragment_path>
# Extracts CPE-authored Closure Payload from an episodic fragment and applies:
#   - working_memory entries → validated + written to Working Memory
#   - session_handoff       → written to session-handoff.json
#   - consolidation_content → appended to session.jsonl for the next session
# ---------------------------------------------------------------------------
mil_apply_closure_payload() {
    local fragment="$1"
    python3 - "$fragment" <<'PYEOF'
import json, os, sys
from datetime import datetime, timezone

fragment_path = sys.argv[1]
root = os.environ.get("FCP_REF_ROOT", "")
handoff_path  = os.path.join(root, "memory", "session-handoff.json")
wm_path       = os.path.join(root, "memory", "working-memory.json")
session_path  = os.path.join(root, "memory", "session.jsonl")

wm_entries    = []
handoff_data  = None
consolidation = ""

try:
    with open(fragment_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                env = json.loads(line)
                if env.get("type") != "CLOSURE_PAYLOAD":
                    continue
                data_raw = env.get("data", "{}")
                data = json.loads(data_raw) if isinstance(data_raw, str) else data_raw
                wm_entries   = data.get("working_memory", [])
                handoff_data = data.get("session_handoff", None)
                consolidation = data.get("consolidation_content", "")
            except Exception:
                pass
except Exception:
    pass

# --- Session Handoff ---
if handoff_data:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    record = {
        "version":      "1.0",
        "updated_at":   ts,
        "pending_tasks": handoff_data.get("pending_tasks", []),
        "next_steps":    handoff_data.get("next_steps", []),
        "notes":         handoff_data.get("notes", ""),
    }
    tmp = handoff_path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(record, f, indent=2)
    os.replace(tmp, handoff_path)
    print("[MIL] Stage 1: Session Handoff written from Closure Payload.", file=sys.stderr)

# --- Working Memory (validate paths exist in Memory Store) ---
if wm_entries:
    try:
        wm = json.load(open(wm_path)) if os.path.exists(wm_path) else {"version": "1.0", "entries": []}
    except Exception:
        wm = {"version": "1.0", "entries": []}
    existing_paths = {e["path"] for e in wm.get("entries", [])}
    added = 0
    for entry in wm_entries:
        raw_path = entry.get("path", "")
        if not raw_path:
            continue
        # Resolve: relative paths are relative to FCP_REF_ROOT
        abs_path = raw_path if os.path.isabs(raw_path) else os.path.join(root, raw_path)
        if not os.path.exists(abs_path):
            print(f"[MIL] Stage 1: WM entry dropped (absent): {raw_path}", file=sys.stderr)
            continue
        store_path = abs_path  # store absolute path
        if store_path not in existing_paths:
            wm["entries"].append({"priority": entry.get("priority", 50), "path": store_path})
            existing_paths.add(store_path)
            added += 1
    # Sort by priority ascending; keep bounded at 20
    wm["entries"].sort(key=lambda e: e.get("priority", 50))
    if len(wm["entries"]) > 20:
        wm["entries"] = wm["entries"][:20]
    tmp = wm_path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(wm, f, indent=2)
    os.replace(tmp, wm_path)
    print(f"[MIL] Stage 1: Working Memory updated ({added} new entries).", file=sys.stderr)

# --- Consolidation Content → append to session.jsonl for next session ---
if consolidation:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    envelope = {
        "actor": "cpe",
        "type":  "CONSOLIDATION",
        "ts":    ts,
        "data":  json.dumps({"content": consolidation}),
    }
    with open(session_path, "a") as f:
        json.dump(envelope, f)
        f.write("\n")
    print("[MIL] Stage 1: Consolidation content written to session.jsonl.", file=sys.stderr)
PYEOF
}

# ---------------------------------------------------------------------------
# mil_update_working_memory <fragment_path>
# Registers a new episodic fragment in working-memory.json if not present.
# Keeps the Working Memory bounded (max 20 entries; oldest removed).
# ---------------------------------------------------------------------------
mil_update_working_memory() {
    local fragment="$1"
    python3 - "$fragment" <<'PYEOF'
import json, os, sys

fragment_path = sys.argv[1]
root = os.environ.get("FCP_REF_ROOT", "")
wm_path = os.path.join(root, "memory", "working-memory.json")

# Relative path from memory/ dir
rel_path = os.path.relpath(fragment_path, os.path.join(root, "memory"))
# Use archive/ or episodic/ relative path for symlink targets
abs_path = fragment_path  # store absolute for now; symlinks will use relative

try:
    wm = json.load(open(wm_path)) if os.path.exists(wm_path) else {"version": "1.0", "entries": []}
except Exception:
    wm = {"version": "1.0", "entries": []}

entries = wm.get("entries", [])
existing = {e["path"] for e in entries}

if fragment_path not in existing:
    entries.append({"priority": 50, "path": fragment_path})

# Keep bounded: max 20 entries
if len(entries) > 20:
    entries = entries[-20:]

wm["entries"] = entries
tmp = wm_path + ".tmp"
with open(tmp, "w") as f:
    json.dump(wm, f, indent=2)
os.replace(tmp, wm_path)
PYEOF

    # Rebuild active_context/ symlinks from Working Memory
    mil_rebuild_active_context
}

# ---------------------------------------------------------------------------
# mil_rebuild_active_context
# Rebuilds memory/active_context/ symlinks from working-memory.json.
# Called at Stage 1 completion and at boot (Phase 5 context assembly).
# ---------------------------------------------------------------------------
mil_rebuild_active_context() {
    [ -f "$WORKING_MEMORY" ] || return 0
    mkdir -p "$ACTIVE_CTX_DIR"

    python3 - <<'PYEOF'
import json, os

root = os.environ.get("FCP_REF_ROOT", "")
wm_path = os.path.join(root, "memory", "working-memory.json")
ctx_dir = os.path.join(root, "memory", "active_context")

try:
    wm = json.load(open(wm_path))
except Exception:
    raise SystemExit(0)

# Remove all existing symlinks (not .keep)
for entry in os.listdir(ctx_dir):
    if entry.startswith("."):
        continue
    p = os.path.join(ctx_dir, entry)
    if os.path.islink(p):
        os.unlink(p)

for i, item in enumerate(wm.get("entries", [])):
    src = item.get("path", "")
    if not src or not os.path.exists(src):
        continue
    priority = item.get("priority", 50)
    basename = os.path.basename(src)
    link_name = f"{priority:03d}-{basename}"
    link_path = os.path.join(ctx_dir, link_name)
    # Use relative path for symlink (portable)
    rel = os.path.relpath(src, ctx_dir)
    try:
        os.symlink(rel, link_path)
    except FileExistsError:
        pass
PYEOF
    echo "[MIL] Stage 1: active_context/ symlinks rebuilt from Working Memory." >&2
}

# ---------------------------------------------------------------------------
# mil_stage2_gc
# Sleep Cycle Stage 2 — Garbage Collection.
# Bounded housekeeping; no CPE invocation.
# ---------------------------------------------------------------------------
mil_stage2_gc() {
    echo "[MIL] Stage 2: Garbage Collection..." >&2

    # Remove stale active_context/ symlinks (target no longer exists)
    if [ -d "$ACTIVE_CTX_DIR" ]; then
        local stale=0
        for link in "$ACTIVE_CTX_DIR"/*; do
            [ -e "$link" ] || [ -L "$link" ] || continue
            [[ "$(basename "$link")" == ".keep" ]] && continue
            if [ -L "$link" ] && [ ! -e "$link" ]; then
                rm -f "$link"
                stale=$((stale + 1))
            fi
        done
        [ "$stale" -gt 0 ] && echo "[MIL] Stage 2: Removed $stale stale active_context symlinks." >&2
    fi

    # Clean spool files older than 2 days
    if [ -d "$SPOOL_DIR" ]; then
        find "$SPOOL_DIR" -name "*.tmp" -mtime +2 -delete 2>/dev/null || true
    fi

    # Clean old presession buffer entries (overflow remnants)
    if [ -d "$PRESESSION_DIR" ]; then
        find "$PRESESSION_DIR" -name "*.msg" -mtime +7 -delete 2>/dev/null || true
    fi

    # Session.jsonl size check — log warning if still large after Stage 1
    if [ -f "$SESSION_FILE" ]; then
        local size
        size=$(wc -c < "$SESSION_FILE" 2>/dev/null || echo 0)
        local s_bytes
        s_bytes=$(python3 -c \
            "import json; print(json.load(open('$FCP_REF_ROOT/state/baseline.json'))['thresholds']['S_bytes'])" \
            2>/dev/null || echo 10485760)
        if [ "$size" -gt "$s_bytes" ]; then
            echo "[MIL] Stage 2: WARNING: session.jsonl is ${size} bytes (> S_bytes=${s_bytes}). Consider session summarization." >&2
        fi
    fi

    echo "[MIL] Stage 2: Garbage Collection complete." >&2
}

# ---------------------------------------------------------------------------
# mil_read_context [budget]
# Assembles the session tail context for the CPE.
# Newest-first up to budget bytes. Skips are logged with CTX_SKIP.
# ---------------------------------------------------------------------------
mil_read_context() {
    local budget="${1:-600000}"
    if [ -f "$SESSION_FILE" ]; then
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

# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    case "${1:-}" in
        drain)   mil_drain_inbox ;;
        stage1)  mil_stage1_consolidate ;;
        stage2)  mil_stage2_gc ;;
        context) mil_read_context "${2:-600000}" ;;
        rebuild-active-context) mil_rebuild_active_context ;;
        *) echo "Usage: $0 {drain|stage1|stage2|context|rebuild-active-context}" >&2; exit 1 ;;
    esac
fi
