#!/bin/bash
# core/cpe.sh — Cognitive Processing Engine (HACA-Arch §4.1)
# Primary reasoning unit. Holds active context window.

set -euo pipefail

# ---------------------------------------------------------------------------
# Initial environment check
# ---------------------------------------------------------------------------
if [ -z "${FCP_REF_ROOT:-}" ]; then
    echo "[CPE] ERROR: FCP_REF_ROOT not set" >&2
    exit 1
fi

# Load libraries
source "$FCP_REF_ROOT/skills/lib/acp.sh"

# ---------------------------------------------------------------------------
# cpe_check_context_window <context_str>
# Emits a session_close action if context size exceeds the critical threshold
# declared in state/baseline.json (context_window_critical_pct).
# ---------------------------------------------------------------------------
cpe_check_context_window() {
    local context="$1"
    local budget="${CONTEXT_BUDGET:-60000}"
    local pct
    pct=$(python3 -c "
import json, os
try:
    d = json.load(open(os.path.join(os.environ['FCP_REF_ROOT'], 'state/baseline.json')))
    print(d['thresholds']['context_window_critical_pct'])
except Exception:
    print(85)
")
    local used critical
    used=${#context}
    critical=$(( budget * pct / 100 ))
    if [ "$used" -ge "$critical" ]; then
        echo '{"action":"session_close","reason":"context_window_critical"}'
    fi
}

# ---------------------------------------------------------------------------
# cpe_assemble_context
# Assembles the full prompt context (Persona, Boot, Env, Memory, Session).
# ---------------------------------------------------------------------------
cpe_assemble_context() {
    local budget="${CONTEXT_BUDGET:-60000}"
    local context=""

    # 1. Persona
    context+=$'\n--- [PERSONA] ---\n'
    for f in "$FCP_REF_ROOT/persona/"*.md; do
        [ -f "$f" ] && context+=$'\n### '"$(basename "$f")"$'\n'$(cat "$f")$'\n'
    done

    # 2. Boot Protocol
    context+=$'\n--- [BOOT PROTOCOL] ---\n'
    [ -f "$FCP_REF_ROOT/BOOT.md" ] && context+=$(cat "$FCP_REF_ROOT/BOOT.md")$'\n'

    # 3. Environment
    context+=$'\n--- [ENV] ---\n'
    [ -f "$FCP_REF_ROOT/state/env.md" ] && context+=$(cat "$FCP_REF_ROOT/state/env.md")$'\n'

    # 4. Working Memory / Active Context (via MIL)
    context+=$'\n--- [ACTIVE CONTEXT] ---\n'
    local active_ctx="$FCP_REF_ROOT/memory/active_context"
    if [ -d "$active_ctx" ]; then
        for link in "$active_ctx"/*; do
            [ -f "$link" ] || [ -L "$link" ] || continue
            [[ "$(basename "$link")" == ".keep" ]] && continue
            context+=$'\n### '"$(basename "$link")"$'\n'$(cat "$link")$'\n'
        done
    fi

    # 5. Session History (via MIL)
    context+=$'\n--- [SESSION HISTORY] ---\n'
    context+=$("$FCP_REF_ROOT/core/mil.sh" context "$budget")

    # Context window guard — emit session_close if critical threshold reached
    cpe_check_context_window "$context"

    echo "$context"
}

# ---------------------------------------------------------------------------
# cpe_query <context>
# Invokes the LLM backend.
# ---------------------------------------------------------------------------
cpe_query() {
    local context="$1"
    "$FCP_REF_ROOT/skills/llm_query.sh" "$context"
}

# ---------------------------------------------------------------------------
# cpe_parse_actions <output>
# Returns only the JSON lines within the fcp-actions block.
# ---------------------------------------------------------------------------
cpe_parse_actions() {
    local output="$1"
    python3 << 'PYEOF'
import sys, re, json
text = sys.stdin.read()
pattern = r'```fcp-actions\n(.*?)```'
match = re.search(pattern, text, re.DOTALL)
if not match: sys.exit(0)
block = match.group(1).strip()
for line in block.splitlines():
    line = line.strip()
    if not line: continue
    try:
        json.loads(line)
        print(line)
    except: pass
PYEOF
    <<< "$output"
}

# CLI entry point
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    case "${1:-}" in
        context) cpe_assemble_context ;;
        query)   cpe_query "$(cat)" ;; # Reads context from stdin
        parse)   cpe_parse_actions "$(cat)" ;;
        *) echo "Usage: $0 {context|query|parse}" >&2; exit 1 ;;
    esac
fi
