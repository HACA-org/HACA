#!/bin/bash
# skills/ws_create/ws_create.sh
#
# Cria um workspace sandboxed em workspaces/<name>/ com sua própria sub-MIL.
#
# Usage (standalone):  ./ws_create.sh <name> <description>
# Usage (via SIL):     params JSON {"name": "...", "description": "..."}

set -euo pipefail

[ -z "${FCP_REF_ROOT:-}" ] && source "$(dirname "$0")/../load_agent_root.sh"
source "$FCP_REF_ROOT/skills/lib/acp.sh"
source "$FCP_REF_ROOT/skills/lib/params.sh"

[[ "${1:-}" == \{* ]] && params_from_json "$1"
WS_NAME=$(param_get NAME        "${1:-}")
DESCRIPTION=$(param_get DESCRIPTION "${2:-}")

if [ -z "$WS_NAME" ]; then
    echo "Usage: $0 <name> <description>" >&2
    exit 1
fi

WS_PATH="$FCP_REF_ROOT/workspaces/${WS_NAME}"

if [ -d "$WS_PATH" ]; then
    echo "[ws_create] ERROR: workspace '${WS_NAME}' already exists." >&2
    exit 1
fi

# Create workspace structure
mkdir -p "${WS_PATH}/context" "${WS_PATH}/inbox" "${WS_PATH}/spool"
touch "${WS_PATH}/context/session.jsonl"

# Write initial goal as ACP envelope in workspace session
GOAL_DATA=$(python3 -c "import json,sys; print(json.dumps({'memory_type':'semantic','tags':['init','goal'],'content':sys.argv[1],'status':'none','entity':sys.argv[2]}))" \
           "$DESCRIPTION" "$WS_NAME")
python3 -c "
import json, time, uuid, zlib
data = '''$GOAL_DATA'''
crc  = format(zlib.crc32(data.encode()) & 0xFFFFFFFF, '08x')
env  = {'actor':'sil','gseq':1,'tx':str(uuid.uuid4()),'seq':1,'eof':True,
        'type':'MSG','ts':'$(date -u +"%Y-%m-%dT%H:%M:%SZ")','data':data,'crc':crc}
print(json.dumps(env))
" >> "${WS_PATH}/context/session.jsonl"

# Register workspace in global MIL
REG_DATA=$(python3 -c "import json,sys; print(json.dumps({'memory_type':'semantic','tags':['workspace','project',sys.argv[1]],'content':'Workspace created: '+sys.argv[1]+'. Path: '+sys.argv[2]+'. Goal: '+sys.argv[3],'status':'none','entity':sys.argv[1]}))" \
           "$WS_NAME" "$WS_PATH" "$DESCRIPTION")
acp_write "el" "MSG" "$REG_DATA" >/dev/null

echo "[ws_create] OK: workspace '${WS_NAME}' initialized at ${WS_PATH}"
