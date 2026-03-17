#!/bin/bash
# skills/summarize_session/summarize_session.sh
#
# Salva um resumo da sessão na MIL antes de um context flush.
# Cria um ACP MSG do tipo 'index' para recuperação rápida futura.
#
# Usage (standalone):  ./summarize_session.sh "resumo..."
# Usage (via SIL):     params JSON {"summary": "...", "next_step": "..."}

set -euo pipefail

[ -z "${FCP_REF_ROOT:-}" ] && source "$(dirname "$0")/../load_agent_root.sh"
source "$FCP_REF_ROOT/skills/lib/acp.sh"
source "$FCP_REF_ROOT/skills/lib/params.sh"

[[ "${1:-}" == \{* ]] && params_from_json "$1"
SUMMARY=$(param_get   SUMMARY   "${1:-}")
NEXT_STEP=$(param_get NEXT_STEP "${2:-}")

if [ -z "$SUMMARY" ]; then
    echo "Usage: $0 <summary> [next_step]" >&2
    exit 1
fi

TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
CONTENT="[Session summary @ ${TS}] ${SUMMARY}"
[ -n "$NEXT_STEP" ] && CONTENT="${CONTENT} | Next: ${NEXT_STEP}"

DATA=$(python3 -c "import json,sys; print(json.dumps({
    'memory_type': 'index',
    'tags': ['session_summary','mind_flush','index'],
    'content': sys.argv[1],
    'status': 'none',
    'entity': 'session'
}))" "$CONTENT")

acp_write "el" "MSG" "$DATA" >/dev/null

# Update pulse
date -u +"%Y-%m-%dT%H:%M:%SZ" > "$FCP_REF_ROOT/state/pulses/sil.alive"

echo "[summarize_session] Summary stored. Safe to flush context."
