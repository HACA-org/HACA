#!/bin/bash
# tools/rotate_probes.sh — Probe pool rotation (HACA-Core §4.8)
#
# With NCD-based drift detection, "probes" are plain-text behavioral snapshots
# stored in state/drift-pool.jsonl. Rotation selects K entries from the pool
# to form the active target set for the next detection cycle.
#
# Each pool entry is an ACP envelope with type DRIFT_PROBE and a data payload
# containing a plain-text behavioral anchor snapshot (no embedding vectors).
#
# The pool SHOULD contain ≥20 entries to provide evasion resistance through
# rotation (HACA-Core §4.8). If the pool is smaller, all entries are used.
#
# Usage:
#   ./tools/rotate_probes.sh [--k <n>] [--dry-run]
#
# After rotation, run tools/calibrate_probes.sh to validate the new selection,
# then update state/integrity.json with the new drift-probes.jsonl SHA-256.

set -euo pipefail

FCP_REF_ROOT="${FCP_REF_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
POOL_FILE="$FCP_REF_ROOT/state/drift-pool.jsonl"
ACTIVE_FILE="$FCP_REF_ROOT/state/drift-probes.jsonl"
K=20
DRY_RUN=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --k)       K="$2"; shift 2 ;;
        --dry-run) DRY_RUN=true; shift ;;
        *) shift ;;
    esac
done

echo "[rotate_probes] Probe pool rotation (HACA-Core §4.8)"
echo "[rotate_probes] Pool:   $POOL_FILE"
echo "[rotate_probes] Active: $ACTIVE_FILE"
echo "[rotate_probes] K=${K} probes to select"
echo ""

# Seed pool from active set if pool doesn't exist yet
if [ ! -f "$POOL_FILE" ]; then
    if [ ! -f "$ACTIVE_FILE" ]; then
        echo "ERROR: Neither pool nor active probe file exists." >&2
        exit 1
    fi
    echo "[rotate_probes] Pool not found — seeding from active set..."
    cp "$ACTIVE_FILE" "$POOL_FILE"
    pool_count=$(grep -c '"type":"DRIFT_PROBE"' "$POOL_FILE" 2>/dev/null || echo 0)
    echo "[rotate_probes] Pool seeded with ${pool_count} probes."
    if [ "$pool_count" -lt "$K" ]; then
        echo "[rotate_probes] WARN: pool has only ${pool_count} entries (need >=${K})."
        echo "[rotate_probes] Add more plain-text behavioral snapshots to state/drift-pool.jsonl."
    fi
    echo ""
fi

# Read all DRIFT_PROBE envelopes from pool
pool_lines=()
while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    if echo "$line" | grep -q '"type":"DRIFT_PROBE"'; then
        pool_lines+=("$line")
    fi
done < "$POOL_FILE"

N=${#pool_lines[@]}
echo "[rotate_probes] Pool size: N=${N}"

if [ "$N" -eq 0 ]; then
    echo "ERROR: No DRIFT_PROBE entries found in pool." >&2
    exit 1
fi

# Random selection of K probes
if [ "$N" -le "$K" ]; then
    echo "[rotate_probes] WARN: pool too small (N=${N} < K=${K}). Using all probes."
    selected=("${pool_lines[@]}")
else
    # Shuffle and take first K (bash-native, no python)
    mapfile -t shuffled < <(printf '%s\n' "${pool_lines[@]}" | shuf)
    selected=("${shuffled[@]:0:$K}")
fi

echo "[rotate_probes] Selected ${#selected[@]} probes."

if [ "$DRY_RUN" = "true" ]; then
    echo "[rotate_probes] DRY RUN — no files written."
    exit 0
fi

# Write new active set atomically
tmp="${ACTIVE_FILE}.tmp"
printf '%s\n' "${selected[@]}" > "$tmp"
mv "$tmp" "$ACTIVE_FILE"

echo "[rotate_probes] Written: $ACTIVE_FILE"
echo ""
echo "[rotate_probes] Next steps:"
echo "  1. bash tools/calibrate_probes.sh       (validate NCD anchor pipeline)"
echo "  2. sha256sum state/drift-probes.jsonl    (update state/integrity.json)"
