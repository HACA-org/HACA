#!/bin/bash
# core/cpe.sh — Cognitive Processing Engine (HACA-Arch §4.1)
# Primary reasoning unit. Holds active context window.

set -euo pipefail

if [ -z "${FCP_REF_ROOT:-}" ]; then
    echo "[CPE] ERROR: FCP_REF_ROOT not set" >&2
    exit 1
fi

source "$FCP_REF_ROOT/skills/lib/acp.sh"

# ---------------------------------------------------------------------------
# cpe_assemble_context
# Assembles the full prompt context sent to the LLM.
# ---------------------------------------------------------------------------
cpe_assemble_context() {
    local budget
    budget=$(python3 -c "
import json, os
try:
    d = json.load(open(os.path.join(os.environ['FCP_REF_ROOT'], 'state/baseline.json')))
    print(d['thresholds']['context_budget_chars'])
except Exception:
    print(600000)
")
    local context=""

    # 1. Persona
    context+=$'\n--- [PERSONA] ---\n'
    for f in "$FCP_REF_ROOT/persona/"*.md; do
        [ -f "$f" ] && context+=$'\n### '"$(basename "$f")"$'\n'$(cat "$f")$'\n'
    done

    # 2. Boot Protocol
    context+=$'\n--- [BOOT PROTOCOL] ---\n'
    [ -f "$FCP_REF_ROOT/BOOT.md" ] && context+=$(cat "$FCP_REF_ROOT/BOOT.md")$'\n'

    # 3. First Activation Protocol (injected when FIRST_BOOT.md is present)
    if [ "${FCP_FAP_MODE:-false}" = "true" ] && [ -f "${FCP_FAP_FILE:-}" ]; then
        context+=$'\n--- [FIRST ACTIVATION PROTOCOL] ---\n'
        context+=$(cat "$FCP_FAP_FILE")$'\n'
    fi

    # 4. Environment
    context+=$'\n--- [ENV] ---\n'
    [ -f "$FCP_REF_ROOT/state/env.md" ] && context+=$(cat "$FCP_REF_ROOT/state/env.md")$'\n'

    # 5. Working Memory / Active Context
    context+=$'\n--- [ACTIVE CONTEXT] ---\n'
    local active_ctx="$FCP_REF_ROOT/memory/active_context"
    if [ -d "$active_ctx" ]; then
        for link in "$active_ctx"/*; do
            [ -f "$link" ] || [ -L "$link" ] || continue
            [[ "$(basename "$link")" == ".keep" ]] && continue
            context+=$'\n### '"$(basename "$link")"$'\n'$(cat "$link")$'\n'
        done
    fi

    # 6. Session History (via MIL)
    context+=$'\n--- [SESSION HISTORY] ---\n'
    context+=$("$FCP_REF_ROOT/core/mil.sh" context "$budget")

    echo "$context"
}

# ---------------------------------------------------------------------------
# cpe_query <context>
# Invokes the LLM backend.
# ---------------------------------------------------------------------------
cpe_query() {
    "$FCP_REF_ROOT/skills/llm_query.sh" "$1"
}

# ---------------------------------------------------------------------------
# cpe_parse_actions
# Reads LLM output from stdin, returns JSON lines from fcp-actions block.
# ---------------------------------------------------------------------------
cpe_parse_actions() {
    python3 - "$1" << 'PYEOF'
import sys, re, json
text = sys.argv[1]
match = re.search(r'```fcp-actions\n(.*?)```', text, re.DOTALL)
if not match:
    sys.exit(0)
for line in match.group(1).strip().splitlines():
    line = line.strip()
    if not line:
        continue
    try:
        json.loads(line)
        print(line)
    except Exception:
        pass
PYEOF
}

# CLI entry point
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    case "${1:-}" in
        context) cpe_assemble_context ;;
        query)   cpe_query "${2:-$(cat)}" ;;
        parse)   cpe_parse_actions "${2:-$(cat)}" ;;
        *) echo "Usage: $0 {context|query|parse}" >&2; exit 1 ;;
    esac
fi
