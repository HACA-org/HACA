#!/bin/bash
# sys_endure/handlers/remove_hook.sh
# Delete a lifecycle hook script and unseal it from integrity.json.
# Requires --confirm.
#
# Required:
#   --event <name>   hook event directory
#   --name <name>    hook filename (with or without numeric prefix)
#   --confirm        must be passed explicitly

set -euo pipefail

FCP_REF_ROOT="${FCP_REF_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"

EVENT="" NAME="" CONFIRM="false"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --event)   EVENT="$2";     shift 2 ;;
        --name)    NAME="$2";      shift 2 ;;
        --confirm) CONFIRM="true"; shift ;;
        *) echo "[remove_hook] Unknown option: $1" >&2; shift ;;
    esac
done

if [ -z "$EVENT" ] || [ -z "$NAME" ]; then
    echo "[remove_hook] ERROR: --event and --name are required" >&2
    exit 1
fi

if [ "$CONFIRM" != "true" ]; then
    echo "[remove_hook] ERROR: --confirm is required for destructive operations" >&2
    exit 1
fi

HOOK_DIR="$FCP_REF_ROOT/hooks/$EVENT"

# Resolve filename — accept with or without numeric prefix
HOOK_FILE=""
if [ -f "$HOOK_DIR/$NAME" ]; then
    HOOK_FILE="$HOOK_DIR/$NAME"
elif [ -f "$HOOK_DIR/$NAME.sh" ]; then
    HOOK_FILE="$HOOK_DIR/$NAME.sh"
else
    # Search by suffix
    HOOK_FILE=$(find "$HOOK_DIR" -maxdepth 1 -name "*_${NAME}.sh" 2>/dev/null | head -1 || true)
fi

if [ -z "$HOOK_FILE" ] || [ ! -f "$HOOK_FILE" ]; then
    echo "[remove_hook] ERROR: hook not found: hooks/$EVENT/*$NAME*" >&2
    exit 1
fi

REL_PATH="hooks/$EVENT/$(basename "$HOOK_FILE")"

# ── Unseal from integrity.json ────────────────────────────────────────────────
python3 - << PYEOF
import json, os

integrity_path = "$FCP_REF_ROOT/state/integrity.json"
with open(integrity_path, 'r') as f:
    integrity = json.load(f)

sigs = integrity.get('signatures', {})
if "$REL_PATH" in sigs:
    del sigs["$REL_PATH"]
    print(f'[remove_hook] Unsealed: $REL_PATH')
else:
    print(f'[remove_hook] Note: $REL_PATH was not sealed (no entry to remove)')

integrity['signatures'] = sigs

tmp = integrity_path + '.tmp'
with open(tmp, 'w') as f:
    json.dump(integrity, f, indent=2)
    f.write('\n')
    f.flush()
    os.fsync(f.fileno())
os.replace(tmp, integrity_path)
PYEOF

# Recompute remaining hashes
"$FCP_REF_ROOT/skills/sys_endure/handlers/seal.sh"

# ── Delete hook file ──────────────────────────────────────────────────────────
rm -f "$HOOK_FILE"
echo "[remove_hook] Deleted: $REL_PATH"

echo ""
echo "[remove_hook] ✓ Hook removed."
echo "[remove_hook]   Run '.endure sync' to commit changes to git."
echo ""
echo "{\"status\":\"ok\",\"hook\":\"$REL_PATH\",\"action\":\"removed\"}"
