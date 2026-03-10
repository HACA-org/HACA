#!/bin/bash
# claude_api.sh - Backend para API da Anthropic (Claude)
# Requer: ANTHROPIC_API_KEY environment variable

if [ "$1" = "--test" ]; then
    # Verifica se API key está configurada e se 'curl' está disponível
    if [ -n "$ANTHROPIC_API_KEY" ] && command -v curl >/dev/null 2>&1; then
        exit 0
    fi
    exit 1
fi

PROMPT="$1"

# Chama API da Anthropic
curl -s https://api.anthropic.com/v1/messages \
    -H "Content-Type: application/json" \
    -H "x-api-key: $ANTHROPIC_API_KEY" \
    -H "anthropic-version: 2023-06-01" \
    -d "{
        \"model\": \"claude-sonnet-4-20250514\",
        \"max_tokens\": 4096,
        \"temperature\": ${LLM_TEMPERATURE:-1},
        \"messages\": [{
            \"role\": \"user\",
            \"content\": $(echo "$PROMPT" | jq -Rs .)
        }]
    }" | jq -r '.content[0].text' 2>/dev/null

exit ${PIPESTATUS[0]}
