#!/bin/bash
# tools/calibrate_probes.sh — Validate NCD probe anchors (FCP RFC §11)
#
# With NCD-based drift detection, probes no longer require pre-computed
# embedding vectors. The anchor is the plain-text identity file itself.
#
# This script validates that:
#   1. persona/identity.md exists and is non-empty (the NCD anchor)
#   2. state/drift-config.json has valid thresholds
#   3. gzip is available (required for NCD computation)
#   4. Runs a dry NCD calculation to confirm the pipeline works
#
# Usage:
#   ./tools/calibrate_probes.sh [--dry-run]
#
# After calibration, no integrity hash update is needed for drift-probes.jsonl
# (NCD uses identity.md as anchor — sealed separately in state/integrity.json).

set -euo pipefail

FCP_REF_ROOT="${FCP_REF_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
ANCHOR_FILE="$FCP_REF_ROOT/persona/identity.md"
TARGET_FILE="$FCP_REF_ROOT/state/env.md"
CONFIG_FILE="$FCP_REF_ROOT/state/drift-config.json"
DRY_RUN=false

if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN=true
fi

echo "[calibrate_probes] NCD probe anchor validation"
echo "[calibrate_probes] Anchor: $ANCHOR_FILE"
echo "[calibrate_probes] Config: $CONFIG_FILE"
echo ""

# 1. Check gzip availability
if ! command -v gzip >/dev/null 2>&1; then
    echo "ERROR: gzip not found. NCD requires gzip (POSIX standard)." >&2
    exit 1
fi
echo "[calibrate_probes] gzip: OK ($(gzip --version 2>&1 | head -1))"

# 2. Check anchor file
if [ ! -f "$ANCHOR_FILE" ] || [ ! -s "$ANCHOR_FILE" ]; then
    echo "ERROR: Anchor file missing or empty: $ANCHOR_FILE" >&2
    exit 1
fi
anchor_bytes=$(wc -c < "$ANCHOR_FILE")
echo "[calibrate_probes] Anchor: OK (${anchor_bytes} bytes)"

# 3. Validate drift-config.json thresholds
if [ ! -f "$CONFIG_FILE" ]; then
    echo "WARN: $CONFIG_FILE not found. Run tools/calibrate_threshold.sh to generate." >&2
else
    warn=$(jq -r '.warning_threshold // "missing"'  "$CONFIG_FILE" 2>/dev/null || echo "missing")
    crit=$(jq -r '.critical_threshold // "missing"' "$CONFIG_FILE" 2>/dev/null || echo "missing")
    algo=$(jq -r '.compression_algorithm // "missing"' "$CONFIG_FILE" 2>/dev/null || echo "missing")
    echo "[calibrate_probes] Config: warning=${warn} critical=${crit} algorithm=${algo}"
    if [ "$warn" = "missing" ] || [ "$crit" = "missing" ]; then
        echo "ERROR: drift-config.json is missing required threshold fields." >&2
        exit 1
    fi
fi

# 4. Dry NCD run (identity.md vs itself — should score ~0.0)
echo ""
echo "[calibrate_probes] Running NCD self-test (identity vs identity, expected ~0.0)..."

c_x=$(gzip -c "$ANCHOR_FILE" | wc -c)
c_xy=$(cat "$ANCHOR_FILE" "$ANCHOR_FILE" | gzip -c | wc -c)
ncd_self=$(awk -v cxy="$c_xy" -v min="$c_x" -v max="$c_x" \
    'BEGIN { printf "%.4f\n", (cxy - min) / max }')
echo "[calibrate_probes] NCD(identity, identity) = ${ncd_self}"

if (( $(awk -v s="$ncd_self" 'BEGIN { print (s > 0.05) ? 1 : 0 }') )); then
    echo "WARN: Self-NCD > 0.05. gzip dictionary may be too small for this anchor file."
else
    echo "[calibrate_probes] Self-test: PASS"
fi

# 5. Live NCD against env.md if available
if [ -f "$TARGET_FILE" ]; then
    echo ""
    echo "[calibrate_probes] Running NCD live test (identity vs env.md)..."
    c_y=$(gzip -c "$TARGET_FILE" | wc -c)
    c_xy=$(cat "$ANCHOR_FILE" "$TARGET_FILE" | gzip -c | wc -c)
    min_c=$c_x; max_c=$c_y
    if [ "$c_y" -lt "$c_x" ]; then min_c=$c_y; max_c=$c_x; fi
    ncd_live=$(awk -v cxy="$c_xy" -v min="$min_c" -v max="$max_c" \
        'BEGIN { printf "%.4f\n", (cxy - min) / max }')
    echo "[calibrate_probes] NCD(identity, env.md) = ${ncd_live}"
    echo "[calibrate_probes] Warning threshold: ${warn:-0.45}"
fi

echo ""
if [ "$DRY_RUN" = "true" ]; then
    echo "[calibrate_probes] DRY RUN — no files written."
else
    echo "[calibrate_probes] Anchor validation complete. No files need updating."
    echo "[calibrate_probes] NCD anchors are plain-text files — no embedding precomputation required."
fi
