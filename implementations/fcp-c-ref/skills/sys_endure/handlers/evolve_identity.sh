#!/bin/bash
# sys_endure/handlers/evolve_identity.sh
# Propose a change to a persona/ file. Validates with drift probes before applying.
#
# Required:
#   --file <path>      relative path inside persona/ (e.g. persona/values.md)
#   --content <text>   new full content for the file
# Optional:
#   --commit-msg <m>   git commit message
#   --dry-run          validate only, do not apply

set -euo pipefail

FCP_REF_ROOT="${FCP_REF_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"

source "$FCP_REF_ROOT/skills/lib/acp.sh"
source "$FCP_REF_ROOT/skills/lib/drift.sh"

TARGET_FILE="" NEW_CONTENT="" COMMIT_MSG="" DRY_RUN="false"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --file)       TARGET_FILE="$2";  shift 2 ;;
        --content)    NEW_CONTENT="$2";  shift 2 ;;
        --commit-msg) COMMIT_MSG="$2";   shift 2 ;;
        --dry-run)    DRY_RUN="true";    shift ;;
        *) echo "[evolve_identity] Unknown option: $1" >&2; shift ;;
    esac
done

if [ -z "$TARGET_FILE" ] || [ -z "$NEW_CONTENT" ]; then
    echo "[evolve_identity] ERROR: --file and --content are required" >&2
    exit 1
fi

ABS_TARGET="$FCP_REF_ROOT/$TARGET_FILE"

# Security: must be under persona/ only
real_target=$(python3 -c "
import os, sys
try:
    p = os.path.realpath(sys.argv[1])
    d = os.path.realpath(sys.argv[2])
    print(p if (p.startswith(d + os.sep) or p == d) else 'DENIED')
except Exception:
    print('DENIED')
" "$ABS_TARGET" "$FCP_REF_ROOT/persona")

if [ "$real_target" = "DENIED" ]; then
    echo "[evolve_identity] ERROR: target must be inside persona/" >&2
    exit 1
fi

if [ ! -f "$real_target" ]; then
    echo "[evolve_identity] ERROR: file not found: $TARGET_FILE" >&2
    exit 1
fi

# ── Write proposed content to temp file ──────────────────────────────────────
PROPOSED="${real_target}.proposed"
printf '%s\n' "$NEW_CONTENT" > "$PROPOSED"

echo "[evolve_identity] Proposed change to: $TARGET_FILE"
echo "[evolve_identity] Running drift probes against proposed identity..."

# ── Swap file, run probes, restore ───────────────────────────────────────────
cp "$real_target" "${real_target}.bak"
cp "$PROPOSED" "$real_target"

drift_result="PASS"
drift_details=""
export _DRIFT_PROBE_FILE="$FCP_REF_ROOT/state/drift-probes.jsonl"
drift_details=$(drift_run_probes --skip-llm 2>&1) || drift_result="FAIL"

if echo "$drift_details" | grep -q '"status":"FAIL"'; then
    drift_result="FAIL"
fi

cp "${real_target}.bak" "$real_target"
rm -f "${real_target}.bak"

if [ "$drift_result" = "FAIL" ]; then
    rm -f "$PROPOSED"
    echo "[evolve_identity] ABORT: drift probes failed — proposed change rejected"
    acp_write "sil" "TRAP" \
        "{\"reason\":\"endure_drift_fail\",\"file\":\"$TARGET_FILE\"}" >/dev/null
    echo "{\"status\":\"rejected\",\"reason\":\"drift_fail\",\"file\":\"$TARGET_FILE\"}"
    exit 0
fi

echo "[evolve_identity] Drift probes: PASS"

if [ "$DRY_RUN" = "true" ]; then
    rm -f "$PROPOSED"
    echo "[evolve_identity] DRY RUN: validation passed, no change applied."
    echo "{\"status\":\"dry_run_pass\",\"file\":\"$TARGET_FILE\"}"
    exit 0
fi

# ── Apply and seal ────────────────────────────────────────────────────────────
cp "$PROPOSED" "$real_target"
rm -f "$PROPOSED"
echo "[evolve_identity] Applied: $TARGET_FILE"

"$FCP_REF_ROOT/skills/sys_endure/handlers/seal.sh"

echo ""
echo "[evolve_identity] ✓ Identity updated: $TARGET_FILE"
echo "[evolve_identity]   Run '.endure sync' to commit changes to git."
echo ""
echo "{\"status\":\"ok\",\"file\":\"$TARGET_FILE\",\"drift\":\"PASS\"}"
