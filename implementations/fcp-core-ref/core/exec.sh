#!/bin/bash
# core/exec.sh — Execution Layer (HACA-Arch §4.3)
# Acts as the boundary for host actuation. Stateless.

set -euo pipefail

# ---------------------------------------------------------------------------
# Initial environment check
# ---------------------------------------------------------------------------
if [ -z "${FCP_REF_ROOT:-}" ]; then
    echo "[EXEC] ERROR: FCP_REF_ROOT not set" >&2
    exit 1
fi

# Load ACP library
source "$FCP_REF_ROOT/skills/lib/acp.sh"

SIL_HELPERS="${SIL_HELPERS:-$FCP_REF_ROOT/core/sil_helpers.py}"
SKILL_INDEX="$FCP_REF_ROOT/skills/index.json"

# ---------------------------------------------------------------------------
# exec_authorize <skill_name>
# Gate 1: Skill Index check. Returns skill path if authorized.
# ---------------------------------------------------------------------------
exec_authorize() {
    local skill_name="$1"
    
    python3 -c "
import json, sys, os
root  = os.environ.get('FCP_REF_ROOT', '')
index_path = os.path.join(root, 'skills', 'index.json')
if not os.path.exists(index_path): sys.exit(1)
index = json.load(open(index_path))
for skill in index.get('skills', []):
    if skill.get('name') == sys.argv[1]:
        if skill.get('authorized', False):
            print(os.path.join(root, skill['path']))
            sys.exit(0)
sys.exit(1)
" "$skill_name" 2>/dev/null
}

# ---------------------------------------------------------------------------
# exec_skill <skill_name> <params_json>
# Gate 1 & 2 validation, then execution with timeout and Action Ledger.
# ---------------------------------------------------------------------------
exec_skill() {
    local skill_name="$1"
    local params_json="$2"
    
    local skill_path
    if ! skill_path=$(exec_authorize "$skill_name"); then
        echo "[EXEC] REJECTED: skill '${skill_name}' not authorized" >&2
        acp_write "el" "SKILL_ERROR" "{\"skill\":\"${skill_name}\",\"reason\":\"not_authorized\"}" >/dev/null
        return 1
    fi

    # Gate 2: Manifest validation (Stateless)
    local manifest="${skill_path}/manifest.json"
    if [ ! -f "$manifest" ]; then
        echo "[EXEC] REJECTED: manifest missing for '${skill_name}'" >&2
        return 1
    fi

    # Action Ledger: Log intent before execution (HACA-Core §4.2)
    # For now, we log every skill request as a pending action.
    local tx
    tx=$(acp_new_tx)
    acp_write "el" "ACTION_PENDING" "{\"skill\":\"${skill_name}\",\"params\":${params_json}}" "$tx" >/dev/null

    echo "[EXEC] Executing: ${skill_name}" >&2
    
    # Locate executable
    local skill_script="${skill_path}/${skill_name}.sh"
    [ -f "$skill_script" ] || skill_script=$(find "$skill_path" -name "*.sh" | head -1)

    if [ ! -f "$skill_script" ]; then
        echo "[EXEC] ERROR: no executable found in ${skill_path}" >&2
        acp_write "el" "SKILL_ERROR" "{\"skill\":\"${skill_name}\",\"reason\":\"not_found\",\"tx\":\"${tx}\"}" >/dev/null
        return 1
    fi

    # Export params as env vars for the script
    local _exported_vars
    _exported_vars=$(python3 -c "
import json, sys
params = json.loads(sys.argv[1])
for k, v in params.items():
    key = ''.join(c if c.isalnum() else '_' for c in k).upper()
    print(f'export SKILL_PARAM_{key}={json.dumps(str(v))}')
" "$params_json" 2>/dev/null)
    eval "$_exported_vars" 2>/dev/null || true

    # Execute with timeout
    local exec_timeout="${SKILL_EXEC_TIMEOUT:-60}"
    local result exit_code=0
    result=$(timeout "$exec_timeout" bash "$skill_script" "$params_json" 2>&1) || exit_code=$?

    if [ "$exit_code" -eq 124 ]; then
        echo "[EXEC] TIMEOUT: ${skill_name} (${exec_timeout}s)" >&2
        acp_write "el" "SKILL_TIMEOUT" "{\"skill\":\"${skill_name}\",\"timeout_s\":${exec_timeout},\"tx\":\"${tx}\"}" >/dev/null
    elif [ "$exit_code" -ne 0 ]; then
        echo "[EXEC] FAILED: ${skill_name} (exit ${exit_code})" >&2
        acp_write "el" "SKILL_ERROR" "{\"skill\":\"${skill_name}\",\"error\":$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$result"),\"exit_code\":${exit_code},\"tx\":\"${tx}\"}" >/dev/null
    else
        echo "[EXEC] SUCCESS: ${skill_name}" >&2
        acp_write "el" "SKILL_RESULT" "{\"skill\":\"${skill_name}\",\"output\":$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$result"),\"tx\":\"${tx}\"}" >/dev/null
    fi

    # Resolve Action Ledger
    acp_write "el" "ACTION_RESOLVED" "{\"tx\":\"${tx}\",\"status\":\"${exit_code}\"}" >/dev/null

    echo "$result"
}

# CLI entry point
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    # Reciprocal SIL Watchdog: check before any skill execution.
    # If SIL is unresponsive, halt execution and escalate to Operator.
    if ! python3 "$SIL_HELPERS" watchdog-check exec 2>&1; then
        echo "[EXEC] HALTED: SIL unresponsive — skill execution suspended." >&2
        exit 1
    fi

    case "${1:-}" in
        execute) exec_skill "${2:-}" "${3:-{}}" ;;
        *) echo "Usage: $0 execute <skill_name> <params_json>" >&2; exit 1 ;;
    esac
fi
