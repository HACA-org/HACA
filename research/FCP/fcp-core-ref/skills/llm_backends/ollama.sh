#!/bin/bash
# ollama.sh - Backend para Ollama local
# Requer: Ollama instalado e rodando (localhost:11434)

if [ "$1" = "--test" ]; then
    # Verifica se Ollama está rodando
    if command -v curl >/dev/null 2>&1; then
        curl -s http://localhost:11434/api/tags >/dev/null 2>&1
        exit $?
    fi
    exit 1
fi

PROMPT="$1"

# Detecta modelo disponível (usa o primeiro da lista)
MODEL=$(curl -s http://localhost:11434/api/tags | jq -r '.models[0].name' 2>/dev/null)

if [ -z "$MODEL" ] || [ "$MODEL" = "null" ]; then
    echo "ERRO: Nenhum modelo Ollama disponível" >&2
    exit 1
fi

# Chama Ollama
curl -s http://localhost:11434/api/generate \
    -d "{
        \"model\": \"$MODEL\",
        \"prompt\": $(echo "$PROMPT" | jq -Rs .),
        \"stream\": false,
        \"options\": {\"temperature\": ${LLM_TEMPERATURE:-0}}
    }" | jq -r '.response' 2>/dev/null

exit ${PIPESTATUS[0]}
