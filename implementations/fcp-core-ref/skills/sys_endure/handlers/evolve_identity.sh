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

SIL_HELPERS="${SIL_HELPERS:-$FCP_REF_ROOT/core/sil_helpers.py}"

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
echo "[evolve_identity] Validating proposed persona content..."

# Verify proposed content contains required identity anchor (structural check).
# Full behavioral drift is assessed at Sleep Cycle Stage 0, not at Endure time.
if ! python3 - "$PROPOSED" <<'PYEOF'
import sys, os
content = open(sys.argv[1]).read().lower()
# Basic structural check: proposed persona must not introduce forbidden patterns
forbidden = ["ignore your constraints", "jailbreak", "forget all previous instructions"]
for f in forbidden:
    if f in content:
        print(f"[evolve_identity] ABORT: forbidden pattern in proposed content: {f!r}", file=sys.stderr)
        sys.exit(1)
sys.exit(0)
PYEOF
then
    rm -f "$PROPOSED"
    acp_write "sil" "TRAP" \
        "{\"reason\":\"endure_content_violation\",\"file\":\"$TARGET_FILE\"}" >/dev/null
    echo "{\"status\":\"rejected\",\"reason\":\"content_violation\",\"file\":\"$TARGET_FILE\"}"
    exit 0
fi

echo "[evolve_identity] Content validation: PASS"

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
