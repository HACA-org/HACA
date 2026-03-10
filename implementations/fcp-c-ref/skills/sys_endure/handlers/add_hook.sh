#!/bin/bash
# sys_endure/handlers/add_hook.sh
# Register a new lifecycle hook script, seal in integrity.json.
#
# Required:
#   --event <name>    event name (e.g. pre_memory_store, post_action)
#   --name <name>     hook name in snake_case (no numeric prefix — auto-assigned)
# Optional:
#   --script <path>   path to script in workspaces/ (creates stub if omitted)
#   --priority <n>    numeric prefix 01-99 (default: next available)

set -euo pipefail

FCP_REF_ROOT="${FCP_REF_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"

EVENT="" NAME="" SCRIPT_SRC="" PRIORITY=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --event)    EVENT="$2";      shift 2 ;;
        --name)     NAME="$2";       shift 2 ;;
        --script)   SCRIPT_SRC="$2"; shift 2 ;;
        --priority) PRIORITY="$2";   shift 2 ;;
        *) echo "[add_hook] Unknown option: $1" >&2; shift ;;
    esac
done

# ── Validation ────────────────────────────────────────────────────────────────
if [ -z "$EVENT" ] || [ -z "$NAME" ]; then
    echo "[add_hook] ERROR: --event and --name are required" >&2
    exit 1
fi

if ! echo "$NAME" | grep -qE '^[a-z][a-z0-9_]*$'; then
    echo "[add_hook] ERROR: name must be snake_case" >&2
    exit 1
fi

HOOK_DIR="$FCP_REF_ROOT/hooks/$EVENT"
mkdir -p "$HOOK_DIR"

# Auto-detect next priority
if [ -z "$PRIORITY" ]; then
    last=$(ls "$HOOK_DIR"/*.sh 2>/dev/null | xargs -I{} basename {} | grep -oE '^[0-9]+' | sort -n | tail -1 || echo "00")
    PRIORITY=$(printf '%02d' $((10#${last:-0} + 1)))
fi

HOOK_FILE="$HOOK_DIR/${PRIORITY}_${NAME}.sh"
REL_PATH="hooks/$EVENT/${PRIORITY}_${NAME}.sh"

if [ -f "$HOOK_FILE" ]; then
    echo "[add_hook] ERROR: hook already exists: $REL_PATH" >&2
    exit 1
fi

# ── Write hook script ─────────────────────────────────────────────────────────
if [ -n "$SCRIPT_SRC" ]; then
    ABS_SCRIPT="$FCP_REF_ROOT/$SCRIPT_SRC"
    if [ ! -f "$ABS_SCRIPT" ]; then
        echo "[add_hook] ERROR: script not found: $SCRIPT_SRC" >&2
        exit 1
    fi
    cp "$ABS_SCRIPT" "$HOOK_FILE"
    chmod +x "$HOOK_FILE"
    echo "[add_hook] Promoted: $SCRIPT_SRC → $REL_PATH"
else
    cat > "$HOOK_FILE" << STUB
#!/usr/bin/env bash
# Hook: $REL_PATH
# Event: $EVENT
# Scaffolded by sys_endure add hook. Implement logic below.
#
# Pre-hooks (pre_*): return exit 1 to abort the operation.
# Post-hooks: return value is ignored.

set -euo pipefail

FCP_REF_ROOT="\${FCP_REF_ROOT:-\$(cd "\$(dirname "\$0")/../.." && pwd)}"

# TODO: implement hook logic for event '$EVENT'
echo "[hook:${EVENT}/${NAME}] Not yet implemented" >&2
exit 0
STUB
    chmod +x "$HOOK_FILE"
    echo "[add_hook] Created stub: $REL_PATH"
fi

# ── Seal ──────────────────────────────────────────────────────────────────────
"$FCP_REF_ROOT/skills/sys_endure/handlers/seal.sh" --add "$REL_PATH"

echo ""
echo "[add_hook] ✓ Hook registered: $REL_PATH"
echo "[add_hook]   Run '.endure sync' to commit changes to git."
echo ""
echo "{\"status\":\"ok\",\"hook\":\"$REL_PATH\"}"
