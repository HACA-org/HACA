#!/usr/bin/env bash
# shell_run — execute a command in the active workspace_focus directory
set -uo pipefail

COMMAND="${FCP_PARAM_COMMAND:?FCP_PARAM_COMMAND is required}"
ENTITY_ROOT="${FCP_ENTITY_ROOT:?FCP_ENTITY_ROOT is required}"

MAX_BYTES=16384
MANIFEST="$ENTITY_ROOT/skills/lib/shell_run/manifest.json"

# Extract base command (first token)
BASE_CMD=$(printf '%s' "$COMMAND" | awk '{print $1}')

# Validate against allowlist declared in manifest.json
ALLOWED=$(python3 -c "
import json, sys
try:
    d = json.load(open('$MANIFEST'))
    print(','.join(d.get('allowlist', [])))
except Exception as e:
    print('', end='')
" 2>/dev/null)

if [ -z "$ALLOWED" ]; then
    echo "Error: could not read allowlist from manifest.json." >&2
    exit 1
fi

if ! printf ',%s,' "$ALLOWED" | grep -qF ",$BASE_CMD,"; then
    echo "Error: '$BASE_CMD' is not in the allowlist." >&2
    echo "Allowed commands: $ALLOWED" >&2
    exit 1
fi

# Resolve workspace_focus
FOCUS_FILE="$ENTITY_ROOT/state/workspace_focus.json"
if [ ! -f "$FOCUS_FILE" ]; then
    echo "Error: workspace_focus not set. Use /work set <subdir> first." >&2
    exit 1
fi

FOCUS=$(python3 -c "
import json, sys
try:
    d = json.load(open('$FOCUS_FILE'))
    p = d.get('path', '').strip()
    if not p:
        sys.exit(1)
    print(p)
except Exception:
    sys.exit(1)
" 2>/dev/null)

if [ $? -ne 0 ] || [ -z "$FOCUS" ]; then
    echo "Error: workspace_focus.json missing or has no 'path' field." >&2
    exit 1
fi

WORK_DIR="$ENTITY_ROOT/workspace/$FOCUS"
if [ ! -d "$WORK_DIR" ]; then
    echo "Error: workspace focus directory not found: workspace/$FOCUS" >&2
    exit 1
fi

# Run command in focus directory, capture output
cd "$WORK_DIR"
RAW=$(bash -c "$COMMAND" 2>&1)
EXIT_CODE=$?

# Truncate if over limit
BYTE_LEN=${#RAW}
if [ "$BYTE_LEN" -gt "$MAX_BYTES" ]; then
    echo "${RAW:0:$MAX_BYTES}"
    echo ""
    echo "[output truncated — $BYTE_LEN bytes total, showing first $MAX_BYTES]"
else
    echo "$RAW"
fi

exit $EXIT_CODE
