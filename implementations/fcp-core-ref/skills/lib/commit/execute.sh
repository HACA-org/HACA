#!/usr/bin/env bash
# commit — stage and commit changes in the active workspace_focus project
set -euo pipefail

PATH_PARAM="${FCP_PARAM_PATH:?FCP_PARAM_PATH is required}"
MESSAGE="${FCP_PARAM_MESSAGE:?FCP_PARAM_MESSAGE is required}"
REMOTE="${FCP_PARAM_REMOTE:-}"
ENTITY_ROOT="${FCP_ENTITY_ROOT:?FCP_ENTITY_ROOT is required}"

FOCUS_FILE="$ENTITY_ROOT/state/workspace_focus.json"

# Require workspace_focus
if [ ! -f "$FOCUS_FILE" ]; then
    echo "error: workspace_focus not set — use /work set <subdir> first" >&2
    exit 1
fi

FOCUS=$(python3 -c "
import json, sys
try:
    d = json.load(open(sys.argv[1]))
    print(d.get('path', ''))
except Exception:
    print('')
" "$FOCUS_FILE")

if [ -z "$FOCUS" ]; then
    echo "error: workspace_focus path is empty" >&2
    exit 1
fi

WORKSPACE_DIR="$ENTITY_ROOT/workspace"
FOCUS_ABS="$WORKSPACE_DIR/$FOCUS"

if [ ! -d "$FOCUS_ABS" ]; then
    echo "error: workspace_focus path does not exist: $FOCUS" >&2
    exit 1
fi

REAL_FOCUS=$(realpath "$FOCUS_ABS")

# Validate that PATH_PARAM is within workspace_focus
TARGET_ABS="$REAL_FOCUS/$PATH_PARAM"
REAL_TARGET=$(realpath "$TARGET_ABS" 2>/dev/null) || REAL_TARGET="$TARGET_ABS"
case "$REAL_TARGET" in
    "$REAL_FOCUS"/*) ;;
    "$REAL_FOCUS")   ;;
    *) echo "error: path '$PATH_PARAM' is outside workspace_focus ($FOCUS)" >&2; exit 1 ;;
esac

# Git operations within the focus project
cd "$REAL_FOCUS"
git add "$REAL_TARGET"
git commit -m "$MESSAGE"

if [ -n "$REMOTE" ]; then
    git push origin HEAD
    echo "Committed and pushed: $PATH_PARAM"
else
    echo "Committed: $PATH_PARAM"
fi
