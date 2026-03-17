#!/usr/bin/env bash
# file_reader — read a file within workspace/
set -euo pipefail

PATH_PARAM="${FCP_PARAM_PATH:?FCP_PARAM_PATH is required}"
ENTITY_ROOT="${FCP_ENTITY_ROOT:?FCP_ENTITY_ROOT is required}"

WORKSPACE_DIR="$ENTITY_ROOT/workspace"
REAL_WORKSPACE=$(realpath "$WORKSPACE_DIR")
TARGET="$WORKSPACE_DIR/$PATH_PARAM"

# Reject paths that don't resolve inside workspace/
REAL_TARGET=$(realpath "$TARGET" 2>/dev/null) || {
    echo "error: path does not exist: $PATH_PARAM" >&2
    exit 1
}
case "$REAL_TARGET" in
    "$REAL_WORKSPACE"/*) ;;
    *) echo "error: path outside workspace/: $PATH_PARAM" >&2; exit 1 ;;
esac

cat "$REAL_TARGET"
