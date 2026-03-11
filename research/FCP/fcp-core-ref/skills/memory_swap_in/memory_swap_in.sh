#!/bin/bash
# memory_swap_in — Symlink VRAM: page archived memory fragment into active_context (FCP §7)
#
# Params (JSON or env vars):
#   query     — keyword(s) to search in archive (space-separated, any match)
#   priority  — numeric prefix for active_context/ link (default: 50)
#   name      — symlink name without priority prefix (default: derived from matched file)
#   date_from — ISO date filter YYYY-MM-DD (optional)
#   date_to   — ISO date filter YYYY-MM-DD (optional)
#   max_files — max fragments to swap in (default: 1)
#   op        — "in" (default) or "out" (remove link by name)
#   swap_out  — name to unlink from active_context (for op=out)
#
# On success: emits ACP MSG with swap_in result and prints symlink paths

set -euo pipefail

FCP_REF_ROOT="${FCP_REF_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$FCP_REF_ROOT/skills/lib/acp.sh"
source "$FCP_REF_ROOT/skills/lib/params.sh"

# Load params
if [[ "${1:-}" == \{* ]]; then
    params_from_json "$1"
fi

QUERY="${SKILL_PARAM_QUERY:-}"
PRIORITY="${SKILL_PARAM_PRIORITY:-50}"
LINK_NAME="${SKILL_PARAM_NAME:-}"
DATE_FROM="${SKILL_PARAM_DATE_FROM:-}"
DATE_TO="${SKILL_PARAM_DATE_TO:-}"
MAX_FILES="${SKILL_PARAM_MAX_FILES:-1}"
OP="${SKILL_PARAM_OP:-in}"
SWAP_OUT_NAME="${SKILL_PARAM_SWAP_OUT:-}"

ARCHIVE_DIR="$FCP_REF_ROOT/memory/archive"
ACTIVE_CTX="$FCP_REF_ROOT/memory/active_context"

# ── op=out ──────────────────────────────────────────────────────────────────
if [ "$OP" = "out" ]; then
    if [ -z "$SWAP_OUT_NAME" ]; then
        echo '{"status":"error","reason":"op=out requires swap_out param"}' >&2
        exit 1
    fi
    removed=()
    for link in "$ACTIVE_CTX"/*"-${SWAP_OUT_NAME}"* "$ACTIVE_CTX/${SWAP_OUT_NAME}"; do
        [ -L "$link" ] || continue
        rm -f "$link"
        removed+=("$(basename "$link")")
    done
    if [ ${#removed[@]} -eq 0 ]; then
        echo '{"status":"not_found","swap_out":"'"$SWAP_OUT_NAME"'"}'
    else
        echo "{\"status\":\"ok\",\"removed\":$(python3 -c "import json,sys; print(json.dumps(sys.argv[1:]))" "${removed[@]}")}"
    fi
    exit 0
fi

# ── op=in ────────────────────────────────────────────────────────────────────
if [ -z "$QUERY" ]; then
    echo '{"status":"error","reason":"query param is required"}' >&2
    exit 1
fi

if [ ! -d "$ARCHIVE_DIR" ]; then
    echo '{"status":"error","reason":"archive directory not found"}' >&2
    exit 1
fi

# Search archive using Python: keyword match + date filter
export _MSI_ARCHIVE="$ARCHIVE_DIR"
export _MSI_QUERY="$QUERY"
export _MSI_DATE_FROM="$DATE_FROM"
export _MSI_DATE_TO="$DATE_TO"
export _MSI_MAX_FILES="$MAX_FILES"

matched_files=$(python3 << 'PYEOF'
import os, json, re, sys
from datetime import datetime

archive  = os.environ['_MSI_ARCHIVE']
query    = os.environ['_MSI_QUERY']
date_from = os.environ.get('_MSI_DATE_FROM', '')
date_to   = os.environ.get('_MSI_DATE_TO', '')
max_files = int(os.environ.get('_MSI_MAX_FILES', '1'))

keywords = [k.lower().strip() for k in query.split() if k.strip()]

def date_ok(fname):
    if not date_from and not date_to:
        return True
    # Extract date from path like archive/2026-01/session-1234.jsonl
    m = re.search(r'(\d{4}-\d{2}-\d{2})', fname)
    if not m:
        return True
    try:
        fdate = datetime.strptime(m.group(1), '%Y-%m-%d').date()
        if date_from and fdate < datetime.strptime(date_from, '%Y-%m-%d').date():
            return False
        if date_to and fdate > datetime.strptime(date_to, '%Y-%m-%d').date():
            return False
    except ValueError:
        pass
    return True

results = []
for root, dirs, files in os.walk(archive):
    dirs.sort()
    for fname in sorted(files):
        if not fname.endswith('.jsonl'):
            continue
        fpath = os.path.join(root, fname)
        if not date_ok(fpath):
            continue
        try:
            with open(fpath, 'r', errors='replace') as f:
                text = f.read().lower()
        except OSError:
            continue
        # Score: count how many keywords appear
        hits = sum(1 for kw in keywords if kw in text)
        if hits > 0:
            results.append((hits, fpath))

# Sort by hit count descending, then path ascending
results.sort(key=lambda x: (-x[0], x[1]))

for hits, path in results[:max_files]:
    print(path)
PYEOF
)

if [ -z "$matched_files" ]; then
    echo '{"status":"no_match","query":"'"$QUERY"'"}'
    exit 0
fi

# Create symlinks in active_context/
linked=()
while IFS= read -r fpath; do
    [ -z "$fpath" ] && continue

    # Derive relative path from FCP_REF_ROOT
    rel_path="${fpath#$FCP_REF_ROOT/}"

    # Derive symlink name from filename if not provided
    if [ -n "$LINK_NAME" ]; then
        sname="$LINK_NAME"
    else
        sname="$(basename "$fpath" .jsonl | tr '/' '-')"
    fi

    link_dest="${ACTIVE_CTX}/${PRIORITY}-${sname}.jsonl"

    # Relative target from active_context/ to the archive file
    rel_target="../${rel_path}"

    ln -sf "$rel_target" "$link_dest"
    linked+=("$link_dest")
done <<< "$matched_files"

if [ ${#linked[@]} -eq 0 ]; then
    echo '{"status":"error","reason":"symlink creation failed"}'
    exit 1
fi

# Emit ACP envelope
linked_json=$(python3 -c "import json,sys; print(json.dumps(sys.argv[1:]))" "${linked[@]}")
result_data=$(python3 -c "
import json, sys
print(json.dumps({
    'status': 'ok',
    'query': sys.argv[1],
    'swapped_in': json.loads(sys.argv[2]),
    'priority': sys.argv[3]
}))
" "$QUERY" "$linked_json" "$PRIORITY")

acp_write "el" "MSG" "$result_data" >/dev/null
echo "$result_data"
