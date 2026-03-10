#!/bin/bash
# skills/snapshot_create/snapshot_create.sh
#
# Cria um snapshot compactado (tar.gz) dos arquivos vitais da entidade FCP.
# Escreve um envelope ACP MSG na MIL registrando o evento.
#
# Usage (standalone):  ./snapshot_create.sh [reason]
# Usage (via SIL):     params JSON {"reason": "..."}

set -euo pipefail

[ -z "${FCP_REF_ROOT:-}" ] && source "$(dirname "$0")/../load_agent_root.sh"
source "$FCP_REF_ROOT/skills/lib/acp.sh"
source "$FCP_REF_ROOT/skills/lib/params.sh"

[[ "${1:-}" == \{* ]] && params_from_json "$1"
REASON=$(param_get REASON "${1:-snapshot manual}")

TIMESTAMP=$(date -u +"%Y%m%dT%H%M%SZ")
SNAPSHOT_NAME="snapshot_${TIMESTAMP}.tar.gz"
SNAPSHOT_PATH="$FCP_REF_ROOT/snapshots/${SNAPSHOT_NAME}"

mkdir -p "$FCP_REF_ROOT/snapshots"

# Arquivos vitais a incluir (conforme FCP — persona, skills, BOOT.md, hooks)
tar -czf "$SNAPSHOT_PATH" -C "$FCP_REF_ROOT" \
    persona \
    skills \
    BOOT.md \
    state/integrity.json \
    state/drift-probes.jsonl \
    hooks \
    .gitignore 2>/dev/null

if [ $? -eq 0 ]; then
    SIZE=$(du -sh "$SNAPSHOT_PATH" | cut -f1)
    DATA=$(python3 -c "import json,sys; print(json.dumps({'memory_type':'episodic','tags':['system','snapshot','backup'],'content':sys.argv[1],'status':'success','entity':'none'}))" \
          "Snapshot criado: ${SNAPSHOT_NAME} (${SIZE}). Motivo: ${REASON}")
    acp_write "el" "MSG" "$DATA" >/dev/null
    echo "[snapshot_create] OK: ${SNAPSHOT_PATH} (${SIZE})"
else
    echo "[snapshot_create] ERROR: tar failed" >&2
    exit 1
fi
