#!/bin/bash
# Uso: ./hook_dispatch.sh <nome_do_evento> [argumentos_para_os_hooks...]

# Carrega FCP_REF_ROOT se necessário
[ -z "$FCP_REF_ROOT" ] && source "$(dirname "$0")/load_agent_root.sh"

EVENT_NAME=$1
shift # Remove o primeiro argumento, deixando apenas os argumentos extras
HOOK_DIR="$FCP_REF_ROOT/hooks/${EVENT_NAME}"

# Se o diretório do evento não existir ou estiver vazio, sai silenciosamente
if [ ! -d "$HOOK_DIR" ] || [ -z "$(ls -A "$HOOK_DIR" 2>/dev/null)" ]; then
    exit 0
fi

# Executa todos os scripts executáveis no diretório do evento
for hook_script in "$HOOK_DIR"/*; do
    if [ -x "$hook_script" ]; then
        # Executa o hook passando os argumentos originais
        # O output de erro é logado para debug, mas não interrompe o fluxo principal
        "$hook_script" "$@" 2>> "${FCP_REF_CONTEXT:-$FCP_REF_ROOT}/memory/hooks_error.log"
        
        # Opcional: Se um hook pre_* retornar erro (exit != 0), podemos abortar a ação principal
        if [ $? -ne 0 ] && [[ "$EVENT_NAME" == pre_* ]]; then
            echo "[HOOK ABORT] O hook $(basename "$hook_script") bloqueou a execução do evento $EVENT_NAME."
            exit 1
        fi
    fi
done

exit 0