#!/bin/bash
# llm_query.sh - Universal LLM Query Dispatcher
# Funciona com qualquer modelo/plataforma disponível no ambiente
# Model-agnostic: tenta backends na ordem de preferência

# Carrega FCP_REF_ROOT se necessário
[ -z "$FCP_REF_ROOT" ] && source "$(dirname "$0")/load_agent_root.sh"

# --drift flag: enforce temperature=0 for deterministic probe responses (RFC §11, HACA-Core §4.7)
DRIFT_MODE=false
if [ "${1:-}" = "--drift" ]; then
    DRIFT_MODE=true
    shift
fi

PROMPT="$1"

if [ -z "$PROMPT" ]; then
    echo "Uso: llm_query.sh [--drift] '<prompt>'" >&2
    exit 1
fi

if [ "$DRIFT_MODE" = "true" ]; then
    export LLM_TEMPERATURE=0
fi

# Lista de backends em ordem de preferência
BACKENDS=(
    "claude_api"
    "ollama"
    "openai"
    "stub"  # Fallback vazio
)

# Função para testar se um backend está disponível
backend_available() {
    local backend="$1"
    local backend_script="$FCP_REF_ROOT/skills/llm_backends/${backend}.sh"

    if [ ! -f "$backend_script" ]; then
        return 1
    fi

    # Testa se o backend está configurado (cada backend tem sua própria lógica)
    "$backend_script" --test 2>/dev/null
    return $?
}

# Tenta cada backend na ordem
for backend in "${BACKENDS[@]}"; do
    if backend_available "$backend"; then
        # Encontrou backend disponível, executa query
        "$FCP_REF_ROOT/skills/llm_backends/${backend}.sh" "$PROMPT"
        exit $?
    fi
done

# Se chegou aqui, nenhum backend disponível
echo "AVISO: Nenhum backend LLM configurado. Consolidação semântica desabilitada." >&2
exit 0
