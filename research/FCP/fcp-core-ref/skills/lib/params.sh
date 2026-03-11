#!/bin/bash
# skills/lib/params.sh — Skill parameter loader
#
# Source this file in skill scripts to read params from either:
#   a) SKILL_PARAM_* env vars (set by SIL when invoked via skill_request)
#   b) Positional args $1, $2, ... (standalone invocation)
#
# Usage inside a skill script:
#   source "$FCP_REF_ROOT/skills/lib/params.sh"
#   # Then call: param_get <KEY> <positional_fallback_value>
#
# Example:
#   TYPE=$(param_get TYPE "$1")
#   TAGS=$(param_get TAGS "$2")
#   CONTENT=$(param_get CONTENT "$3")

# param_get <KEY> [fallback]
# Returns SKILL_PARAM_<KEY> if set, else the fallback value.
param_get() {
    local key="${1^^}"  # uppercase
    local fallback="${2:-}"
    local env_var="SKILL_PARAM_${key}"
    local val="${!env_var:-}"
    # Strip surrounding JSON quotes if present (SIL exports JSON-encoded strings)
    if [ -n "$val" ]; then
        val=$(python3 -c "import json,sys; v=sys.argv[1]; print(json.loads(v) if v.startswith('\"') else v)" \
              "$val" 2>/dev/null || echo "$val")
    fi
    echo "${val:-$fallback}"
}

# params_from_json <json_string>
# Exports SKILL_PARAM_* for every key in the JSON object.
# Call this at the top of a skill if you want to load from $1 JSON directly.
params_from_json() {
    local json="${1:-}"
    [ -z "$json" ] && return 0
    local exports
    exports=$(python3 -c "
import json, sys
try:
    params = json.loads(sys.argv[1])
    for k, v in params.items():
        key = ''.join(c if c.isalnum() else '_' for c in k).upper()
        print(f'export SKILL_PARAM_{key}={json.dumps(str(v))}')
except Exception:
    pass
" "$json" 2>/dev/null)
    eval "$exports" 2>/dev/null || true
}
