#!/bin/bash
# skills/memory_store/memory_store.sh
#
# Persiste um fragmento de memória na MIL via o mecanismo spool→inbox (FCP §5.1).
# Cada escrita produz um envelope ACP atômico em memory/inbox/.
# O SIL drena inbox/ → session.jsonl durante o boot.
#
# Usage:
#   ./memory_store.sh <type> <tags_csv> <content> [status] [entity]
#
# Arguments:
#   type    — episodic | semantic | index
#   tags    — tags separadas por vírgula (ex: "python,bug,fix")
#   content — conteúdo textual a ser salvo
#   status  — (opcional) resultado associado: success | failure | none
#   entity  — (opcional) entidade/tópico para semantic/index
#
# ACP envelope type used: MSG
# Data payload schema:
#   {"memory_type":"<type>","tags":[...],"content":"...","status":"...","entity":"..."}

set -euo pipefail

# --- Bootstrap ---
[ -z "${FCP_REF_ROOT:-}" ] && source "$(dirname "$0")/../load_agent_root.sh"
source "$FCP_REF_ROOT/skills/lib/acp.sh"
source "$FCP_REF_ROOT/skills/lib/params.sh"

# --- Args: accept JSON from SIL ($1) or positional args ---
[ -n "${1:-}" ] && params_from_json "${1:-}"

MEMORY_TYPE=$(param_get TYPE    "${1:-}")
TAGS_CSV=$(param_get    TAGS    "${2:-}")
CONTENT=$(param_get     CONTENT "${3:-}")
STATUS=$(param_get      STATUS  "${4:-none}")
ENTITY=$(param_get      ENTITY  "${5:-none}")

if [ -z "$MEMORY_TYPE" ] || [ -z "$CONTENT" ]; then
    echo "Usage: $0 <type> <tags_csv> <content> [status] [entity]" >&2
    exit 1
fi

case "$MEMORY_TYPE" in
    episodic|semantic|index) ;;
    *)
        echo "[memory_store] ERROR: unknown type '$MEMORY_TYPE'. Use: episodic | semantic | index" >&2
        exit 1
        ;;
esac

# --- Pre-store hooks ---
"$FCP_REF_ROOT/hooks/hook_dispatch.sh" "pre_memory_store" \
    "$FCP_REF_ROOT/memory/session.jsonl" "$TAGS_CSV" "$CONTENT" || {
    echo "[memory_store] Aborted by pre_memory_store hook." >&2
    exit 1
}

# --- Build structured data payload (JSON-serialized string) ---
DATA=$(python3 -c "
import json, sys
memory_type, tags_csv, content, status, entity = \
    sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5]
tags = [t.strip() for t in tags_csv.split(',') if t.strip()]
payload = {
    'memory_type': memory_type,
    'tags': tags,
    'content': content,
    'status': status,
    'entity': entity,
}
print(json.dumps(payload, ensure_ascii=False))
" "$MEMORY_TYPE" "$TAGS_CSV" "$CONTENT" "$STATUS" "$ENTITY")

# Validate 4KB rule before writing
DATA_LEN=${#DATA}
if [ "$DATA_LEN" -gt 4000 ]; then
    echo "[memory_store] ERROR: payload exceeds 4000 bytes (${DATA_LEN}). Truncate content." >&2
    exit 1
fi

# --- Write ACP envelope via spool→inbox ---
MSG_FILE=$(acp_write "el" "MSG" "$DATA")

echo "[memory_store] OK: envelope written → ${MSG_FILE}"
