#!/bin/bash
# sys_endure/handlers/evolve_boot.sh
# Propose a change to BOOT.md, the system instruction manual.
# No drift probes — BOOT.md is instructions, not identity.
# Requires operator to provide the full new content.
#
# Required:
#   --content <text>   new full content for BOOT.md
# Optional:
#   --commit-msg <m>   git commit message
#   --dry-run          validate only, do not apply

set -euo pipefail

FCP_REF_ROOT="${FCP_REF_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"

source "$FCP_REF_ROOT/skills/lib/acp.sh"

NEW_CONTENT="" COMMIT_MSG="" DRY_RUN="false"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --content)    NEW_CONTENT="$2"; shift 2 ;;
        --commit-msg) COMMIT_MSG="$2";  shift 2 ;;
        --dry-run)    DRY_RUN="true";   shift ;;
        *) echo "[evolve_boot] Unknown option: $1" >&2; shift ;;
    esac
done

if [ -z "$NEW_CONTENT" ]; then
    echo "[evolve_boot] ERROR: --content is required" >&2
    exit 1
fi

BOOT_FILE="$FCP_REF_ROOT/BOOT.md"
PROPOSED="${BOOT_FILE}.proposed"
printf '%s\n' "$NEW_CONTENT" > "$PROPOSED"

echo "[evolve_boot] Proposed change to BOOT.md ($(wc -c < "$PROPOSED") bytes)"

if [ "$DRY_RUN" = "true" ]; then
    rm -f "$PROPOSED"
    echo "[evolve_boot] DRY RUN: content written and validated, no change applied."
    echo "{\"status\":\"dry_run_pass\",\"file\":\"BOOT.md\"}"
    exit 0
fi

# ── Apply and seal ────────────────────────────────────────────────────────────
cp "$PROPOSED" "$BOOT_FILE"
rm -f "$PROPOSED"
echo "[evolve_boot] Applied: BOOT.md"

"$FCP_REF_ROOT/skills/sys_endure/handlers/seal.sh"

echo ""
echo "[evolve_boot] ✓ BOOT.md updated."
echo "[evolve_boot]   Run '.endure sync' to commit changes to git."
echo ""
echo "{\"status\":\"ok\",\"file\":\"BOOT.md\"}"
