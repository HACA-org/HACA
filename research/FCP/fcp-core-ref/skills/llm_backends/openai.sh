#!/bin/bash
# openai.sh - Backend para OpenAI API
# Requer: OPENAI_API_KEY environment variable

if [ "$1" = "--test" ]; then
    # Verifica se API key está configurada e se 'curl' está disponível
    if [ -n "$OPENAI_API_KEY" ] && command -v curl >/dev/null 2>&1; then
        exit 0
    fi
    exit 1
fi

PROMPT="$1"

# Chama OpenAI API
curl -s https://api.openai.com/v1/chat/completions \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $OPENAI_API_KEY" \
    -d "{
        \"model\": \"gpt-4\",
        \"temperature\": ${LLM_TEMPERATURE:-0},
        \"messages\": [{
            \"role\": \"user\",
            \"content\": $(echo "$PROMPT" | jq -Rs .)
        }]
    }" | jq -r '.choices[0].message.content' 2>/dev/null

exit ${PIPESTATUS[0]}
