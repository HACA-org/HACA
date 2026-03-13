#!/usr/bin/env bash
# file_writer — write a file within workspace/
set -euo pipefail

PATH_PARAM="${FCP_PARAM_PATH:?FCP_PARAM_PATH is required}"
CONTENT="${FCP_PARAM_CONTENT:?FCP_PARAM_CONTENT is required}"
ENTITY_ROOT="${FCP_ENTITY_ROOT:?FCP_ENTITY_ROOT is required}"

WORKSPACE_DIR="$ENTITY_ROOT/workspace"
REAL_WORKSPACE=$(realpath "$WORKSPACE_DIR")
TARGET="$WORKSPACE_DIR/$PATH_PARAM"
TARGET_DIR=$(dirname "$TARGET")

# Create parent dirs and resolve to check containment
mkdir -p "$TARGET_DIR"
REAL_TARGET_DIR=$(realpath "$TARGET_DIR")
case "$REAL_TARGET_DIR" in
    "$REAL_WORKSPACE"/*) ;;
    "$REAL_WORKSPACE")   ;;
    *) echo "error: path outside workspace/: $PATH_PARAM" >&2; exit 1 ;;
esac

printf '%s' "$CONTENT" > "$TARGET"
echo "Written: workspace/$PATH_PARAM"
