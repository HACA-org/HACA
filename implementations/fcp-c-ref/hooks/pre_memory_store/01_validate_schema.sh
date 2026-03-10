#!/usr/bin/env bash
# Hook: pre_memory_store/01_validate_schema.sh
# Executa ANTES de salvar memória
# Valida que o JSON está bem formado
# Retorna exit 1 se inválido (aborta operação)

set -euo pipefail

# Parâmetros recebidos do hook_dispatch.sh
TARGET_FILE="$1"    # Arquivo que será escrito
TAGS="$2"           # Tags da memória
CONTENT="$3"        # Conteúdo da memória

# Validação básica: content não pode estar vazio
if [[ -z "$CONTENT" ]]; then
    echo "❌ [pre_memory_store] Erro: Conteúdo vazio detectado" >&2
    exit 1
fi

# Validação de JSON: tenta parsear o content como JSON se parece com JSON
# (heurística: começa com { ou [)
if [[ "$CONTENT" =~ ^\{.*\}$ ]] || [[ "$CONTENT" =~ ^\[.*\]$ ]]; then
    # Validar JSON usando Python3 (nativo, sem jq)
    if ! python3 -c "import json; json.loads('''$CONTENT''')" 2>/dev/null; then
        echo "❌ [pre_memory_store] Erro: JSON malformado no content" >&2
        echo "Content: $CONTENT" >&2
        exit 1
    fi
fi

# Validação de tags: pelo menos uma tag deve existir
if [[ -z "$TAGS" ]] || [[ "$TAGS" == "none" ]]; then
    echo "⚠️  [pre_memory_store] Aviso: Nenhuma tag fornecida (recomendado adicionar tags)" >&2
    # Apenas warning, não aborta
fi

# Validação de comprimento: ACP envelopes max 4000 bytes (FCP §4 — 4KB Rule)
CONTENT_LENGTH=${#CONTENT}
if [[ $CONTENT_LENGTH -gt 4000 ]]; then
    echo "❌ [pre_memory_store] Erro: Content muito longo ($CONTENT_LENGTH bytes > 4000 bytes ACP limit)" >&2
    echo "Considere resumir ou dividir em múltiplas entradas" >&2
    exit 1
fi

# Se chegou aqui, validação passou
echo "✅ [pre_memory_store] Validação OK: ${CONTENT_LENGTH} bytes, tags: $TAGS"
exit 0
