#!/bin/bash
# tools/calibrate_threshold.sh — Calibrate NCD drift thresholds (HACA-Core §4.5.1)
#
# Derives empirical warning and critical thresholds for NCD-based drift detection
# by measuring the NCD of the anchor (persona/identity.md) against:
#   - Itself (baseline: expected ~0.0)
#   - Progressively perturbed versions (adversarial sensitivity)
#   - Random noise file (upper bound: expected ~1.0)
#
# Outputs:
#   warning_threshold  — NCD at which Tier 2 Oracle is triggered
#   critical_threshold — NCD at which execution aborts immediately
#
# Usage:
#   ./tools/calibrate_threshold.sh [--dry-run]
#
# After calibration, review state/drift-config.json and adjust thresholds
# based on your deployment context.

set -euo pipefail

FCP_REF_ROOT="${FCP_REF_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
ANCHOR_FILE="$FCP_REF_ROOT/persona/identity.md"
CONFIG_OUT="$FCP_REF_ROOT/state/drift-config.json"
DRY_RUN=false

for arg in "$@"; do
    [[ "$arg" == "--dry-run" ]] && DRY_RUN=true
done

echo "[calibrate_threshold] NCD drift threshold calibration"
echo "[calibrate_threshold] Anchor: $ANCHOR_FILE"
echo ""

if [ ! -f "$ANCHOR_FILE" ] || [ ! -s "$ANCHOR_FILE" ]; then
    echo "ERROR: Anchor file missing or empty: $ANCHOR_FILE" >&2
    exit 1
fi

TMPDIR_CAL=$(mktemp -d)
trap 'rm -rf "$TMPDIR_CAL"' EXIT

# Helper: compute NCD between two files
ncd() {
    local f1="$1" f2="$2"
    local cx cy cxy min_c max_c
    cx=$(gzip -c "$f1" | wc -c)
    cy=$(gzip -c "$f2" | wc -c)
    cxy=$(cat "$f1" "$f2" | gzip -c | wc -c)
    min_c=$cx; max_c=$cy
    if [ "$cy" -lt "$cx" ]; then min_c=$cy; max_c=$cx; fi
    awk -v cxy="$cxy" -v min="$min_c" -v max="$max_c" \
        'BEGIN { printf "%.4f\n", (cxy - min) / max }'
}

# Phase 1: Baseline (identity vs itself)
echo "[calibrate_threshold] Phase 1: Baseline (NCD self-similarity)..."
ncd_self=$(ncd "$ANCHOR_FILE" "$ANCHOR_FILE")
echo "  NCD(identity, identity) = ${ncd_self}  [expected: ~0.0]"

# Phase 2: Adversarial (progressively perturbed copies)
echo ""
echo "[calibrate_threshold] Phase 2: Adversarial sensitivity (word removal)..."

anchor_words=( $(cat "$ANCHOR_FILE") )
total_words=${#anchor_words[@]}

declare -a perturb_results
levels=(10 25 50 75 90)

for pct in "${levels[@]}"; do
    keep=$(( total_words * (100 - pct) / 100 ))
    [ "$keep" -lt 1 ] && keep=1
    perturbed_file="$TMPDIR_CAL/perturb_${pct}.txt"
    # Shuffle and truncate to simulate removal
    printf '%s\n' "${anchor_words[@]}" | shuf | head -n "$keep" > "$perturbed_file"
    score=$(ncd "$ANCHOR_FILE" "$perturbed_file")
    perturb_results+=("$pct:$score")
    echo "  removal=${pct}%  NCD=${score}"
done

# Phase 3: Upper bound (random noise)
echo ""
echo "[calibrate_threshold] Phase 3: Upper bound (random noise)..."
noise_file="$TMPDIR_CAL/noise.txt"
head -c "$(wc -c < "$ANCHOR_FILE")" /dev/urandom | base64 | head -c "$(wc -c < "$ANCHOR_FILE")" > "$noise_file"
ncd_noise=$(ncd "$ANCHOR_FILE" "$noise_file")
echo "  NCD(identity, noise) = ${ncd_noise}  [expected: ~0.8-1.0]"

# Phase 4: Derive thresholds
echo ""
echo "[calibrate_threshold] Phase 4: Threshold derivation..."

# warning = NCD at ~25% word removal (noticeable but not catastrophic drift)
warn_raw=""
for r in "${perturb_results[@]}"; do
    [[ "$r" == "25:"* ]] && warn_raw="${r#25:}"
done
[ -z "$warn_raw" ] && warn_raw="0.45"

# critical = NCD at ~75% word removal (severe structural divergence)
crit_raw=""
for r in "${perturb_results[@]}"; do
    [[ "$r" == "75:"* ]] && crit_raw="${r#75:}"
done
[ -z "$crit_raw" ] && crit_raw="0.65"

# Round and apply safety bounds
warning_threshold=$(awk -v v="$warn_raw" 'BEGIN { v=v+0; if(v<0.30) v=0.30; if(v>0.60) v=0.60; printf "%.2f\n", v }')
critical_threshold=$(awk -v v="$crit_raw" 'BEGIN { v=v+0; if(v<0.55) v=0.55; if(v>0.85) v=0.85; printf "%.2f\n", v }')

echo "  warning_threshold  = ${warning_threshold}  (NCD at ~25% word removal)"
echo "  critical_threshold = ${critical_threshold}  (NCD at ~75% word removal)"

config=$(cat <<EOF
{
  "drift_measurement": "ncd",
  "compression_algorithm": "gzip",
  "calibrated_at": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "anchor": "persona/identity.md",
  "ncd_baseline": ${ncd_self},
  "ncd_noise_upper": ${ncd_noise},
  "warning_threshold": ${warning_threshold},
  "critical_threshold": ${critical_threshold},
  "note": "warning triggers Tier 2 LLM Oracle; critical triggers immediate DRIFT_FAULT without Oracle."
}
EOF
)

echo ""
if [ "$DRY_RUN" = "true" ]; then
    echo "[calibrate_threshold] DRY RUN — config not written."
    echo "$config"
else
    tmp="${CONFIG_OUT}.tmp"
    echo "$config" > "$tmp"
    mv "$tmp" "$CONFIG_OUT"
    echo "[calibrate_threshold] Written: $CONFIG_OUT"
fi
