#!/bin/bash
# sys_endure/handlers/sync.sh
# Commit staged evolution changes to git. Optionally push to remote.
#
# Optional:
#   --remote          also push to remote after commit
#   --message <m>     custom commit message

set -euo pipefail

FCP_REF_ROOT="${FCP_REF_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"

source "$FCP_REF_ROOT/skills/lib/acp.sh"

REMOTE="false" MSG=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --remote)       REMOTE="true"; shift ;;
        --message|-m)   MSG="$2"; shift 2 ;;
        *) echo "[sync] Unknown option: $1" >&2; shift ;;
    esac
done

cd "$FCP_REF_ROOT"

if ! git rev-parse --git-dir > /dev/null 2>&1; then
    echo "[sync] ERROR: not a git repository" >&2
    exit 1
fi

# Stage integrity-critical files
git add state/integrity.json skills/index.json 2>/dev/null || true

# Stage skill and hook files (new and modified)
git add skills/*/manifest.json 2>/dev/null || true
git add skills/*/*.sh 2>/dev/null || true
git add hooks/ 2>/dev/null || true
git add BOOT.md persona/ 2>/dev/null || true

if git diff --cached --quiet; then
    echo "[sync] Nothing to commit — working tree is clean."
    exit 0
fi

# Show what will be committed
echo "[sync] Staged changes:"
git diff --cached --name-status | sed 's/^/  /'

COMMIT_MSG="${MSG:-sys_endure: system evolution

sys_endure: automated evolution commit}"

git commit -m "$COMMIT_MSG"
HASH=$(git rev-parse HEAD)
echo "[sync] Committed: $HASH"

if [ "$REMOTE" = "true" ]; then
    git push
    echo "[sync] Pushed to remote."
fi

acp_write "sil" "MSG" \
    "{\"event\":\"endure_sync\",\"commit\":\"$HASH\",\"remote\":$REMOTE}" \
    >/dev/null 2>&1 || true

echo ""
echo "{\"status\":\"ok\",\"commit\":\"$HASH\",\"pushed\":$REMOTE}"
