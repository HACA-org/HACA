#!/bin/bash
# hello_world — Uma skill de teste que emite uma sauda????o personalizada
# Scaffolded by sys_endure add skill. Implement logic below.

set -euo pipefail

[ -z "$FCP_REF_ROOT" ] && source "$(dirname "$0")/../load_agent_root.sh"
source "$FCP_REF_ROOT/skills/lib/acp.sh"
source "$FCP_REF_ROOT/skills/lib/params.sh"

# --- Args ---
[ -n "${1:-}" ] && params_from_json "${1:-}"
MESSAGE=$(param_get MESSAGE "${1:-Hello from Agent-Zero!}")

echo "[hello_world] Executing with message: $MESSAGE"

# Log to session via ACP
acp_write "el" "MSG" "{\"event\": \"hello_world_executed\", \"message\": \"$MESSAGE\"}" > /dev/null

echo "[hello_world] Done."
exit 0
