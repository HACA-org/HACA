#!/bin/bash
# skills/snapshot_list/snapshot_list.sh
#
# Lista todos os snapshots disponíveis em snapshots/, ordenados do mais recente.

set -euo pipefail

[ -z "${FCP_REF_ROOT:-}" ] && source "$(dirname "$0")/../load_agent_root.sh"

SNAPSHOT_DIR="$FCP_REF_ROOT/snapshots"

if [ ! -d "$SNAPSHOT_DIR" ] || [ -z "$(ls -A "$SNAPSHOT_DIR" 2>/dev/null | grep '\.tar\.gz')" ]; then
    echo "(no snapshots found)"
    exit 0
fi

echo "Available snapshots:"
ls -lht "$SNAPSHOT_DIR"/*.tar.gz 2>/dev/null | awk '{printf "  %s  %s  %s\n", $6, $7, $9}' | \
    sed "s|${SNAPSHOT_DIR}/||"
