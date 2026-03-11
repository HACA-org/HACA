#!/bin/bash
# skills/memory_retrieve/memory_retrieve.sh
#
# Busca fragmentos de memória na MIL lendo envelopes ACP de:
#   1. memory/inbox/*.msg   — escritas recentes ainda não drenadas pelo SIL
#   2. memory/session.jsonl — log principal já consolidado
#
# Usage:
#   ./memory_retrieve.sh <type> <query> [limit] [--inbox-only|--session-only]
#
# Arguments:
#   type    — episodic | semantic | index | * (qualquer tipo)
#   query   — substring a buscar no conteúdo ou tags (case-insensitive)
#   limit   — máximo de resultados (default: 10)
#
# Flags:
#   --inbox-only    busca apenas em memory/inbox/
#   --session-only  busca apenas em memory/session.jsonl

set -euo pipefail

[ -z "${FCP_REF_ROOT:-}" ] && source "$(dirname "$0")/../load_agent_root.sh"
source "$FCP_REF_ROOT/skills/lib/params.sh"

# --- Parse args: accept JSON from SIL ($1) or positional/flag args ---
INBOX_ONLY=false
SESSION_ONLY=false

# If first arg looks like JSON, load params from it
if [[ "${1:-}" == \{* ]]; then
    params_from_json "$1"
    MEMORY_TYPE=$(param_get TYPE  "")
    QUERY=$(param_get       QUERY "")
    LIMIT=$(param_get       LIMIT "10")
else
    MEMORY_TYPE=""
    QUERY=""
    LIMIT=10
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --inbox-only)   INBOX_ONLY=true;   shift ;;
            --session-only) SESSION_ONLY=true;  shift ;;
            *)
                [ -z "$MEMORY_TYPE" ] && MEMORY_TYPE="$1" && shift && continue
                [ -z "$QUERY"       ] && QUERY="$1"       && shift && continue
                LIMIT="$1"; shift ;;
        esac
    done
fi

if [ -z "$MEMORY_TYPE" ] || [ -z "$QUERY" ]; then
    echo "Usage: $0 <type> <query> [limit] [--inbox-only|--session-only]" >&2
    exit 1
fi

# --- Collect source files ---
SOURCES=()

if [ "$SESSION_ONLY" = "false" ]; then
    INBOX="$FCP_REF_ROOT/memory/inbox"
    if [ -d "$INBOX" ]; then
        for f in "$INBOX"/*.msg; do
            [ -f "$f" ] && SOURCES+=("INBOX:$f")
        done
    fi
fi

if [ "$INBOX_ONLY" = "false" ]; then
    SESSION="$FCP_REF_ROOT/memory/session.jsonl"
    [ -f "$SESSION" ] && SOURCES+=("SESSION:$SESSION")
fi

if [ ${#SOURCES[@]} -eq 0 ]; then
    echo "--- No sources found ---"
    exit 0
fi

# --- Export for Python ---
export ACP_SOURCES="${SOURCES[*]:-}"
export ACP_QUERY="$QUERY"
export ACP_LIMIT="$LIMIT"
export ACP_TYPE="$MEMORY_TYPE"

echo "--- ACP memory search: type='${MEMORY_TYPE}' query='${QUERY}' limit=${LIMIT} ---"
echo ""

python3 << 'PYEOF'
import json, os, sys

sources_str = os.environ.get('ACP_SOURCES', '')
query       = os.environ.get('ACP_QUERY', '').lower()
limit       = int(os.environ.get('ACP_LIMIT', '10'))
filter_type = os.environ.get('ACP_TYPE', '*')

results = []

for source_spec in sources_str.split():
    label, path = source_spec.split(':', 1)
    if not os.path.isfile(path):
        continue
    with open(path, 'r', errors='replace') as fh:
        for raw_line in fh:
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                envelope = json.loads(raw_line)
            except json.JSONDecodeError:
                continue

            # Only process MSG envelopes (memory records)
            if envelope.get('type') != 'MSG':
                continue

            # Parse the nested data payload
            data_str = envelope.get('data', '')
            try:
                payload = json.loads(data_str)
            except (json.JSONDecodeError, TypeError):
                # Legacy records: treat data as plain content
                payload = {'memory_type': 'unknown', 'content': data_str, 'tags': [], 'status': 'none', 'entity': 'none'}

            mem_type = payload.get('memory_type', 'unknown')

            # Filter by type (* = all)
            if filter_type != '*' and mem_type != filter_type:
                continue

            # Filter by query substring in content or tags
            content  = payload.get('content', '')
            tags_str = ','.join(payload.get('tags', []))
            if query not in content.lower() and query not in tags_str.lower():
                continue

            results.append({
                '_source':  label,
                '_ts':      envelope.get('ts', ''),
                '_actor':   envelope.get('actor', ''),
                'type':     mem_type,
                'tags':     payload.get('tags', []),
                'content':  content,
                'status':   payload.get('status', ''),
                'entity':   payload.get('entity', ''),
            })

# Sort newest-first, then limit
results.sort(key=lambda x: x['_ts'], reverse=True)
results = results[:limit]

if not results:
    print("(no results)")
else:
    for r in results:
        ts      = r['_ts'][:19] if r['_ts'] else 'unknown'
        src     = f"[{r['_source']:7}]"
        tags    = ','.join(r['tags'])
        content = r['content'][:100]
        status  = f" status={r['status']}" if r['status'] and r['status'] != 'none' else ''
        entity  = f" entity={r['entity']}" if r['entity'] and r['entity'] != 'none' else ''
        print(f"{ts} {src} [{r['type']:8}] tags={tags:<24}{status}{entity}")
        print(f"  └─ {content}")
        print()

PYEOF

echo "---"
