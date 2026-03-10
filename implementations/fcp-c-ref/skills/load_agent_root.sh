#!/bin/bash
# load_agent_root.sh - Carrega a localização do agente (alta performance)
# Este script lê o FCP_REF_ROOT já descoberto pelo recon_env.sh no boot.
#
# Uso: [ -z "$FCP_REF_ROOT" ] && source "$(dirname "$0")/load_agent_root.sh"
#
# IMPORTANTE: recon_env.sh deve ser executado no boot para criar o cache.

# Estratégia 1: Ler de variáveis de ambiente (se já estão exportadas)
if [ -n "$FCP_REF_ROOT" ]; then
    # Valida que FCP_REF_ROOT não foi corrompida
    if [ -f "$FCP_REF_ROOT/BOOT.md" ]; then
        return 0 2>/dev/null || exit 0
    fi
    # Corrompida - limpa e re-detecta
    unset FCP_REF_ROOT
    unset FCP_REF_CONTEXT
fi

# Estratégia 2: Detecta dinamicamente subindo níveis até achar BOOT.md
if [ -n "${BASH_SOURCE[0]}" ]; then
    CURRENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
else
    CURRENT_DIR="$(cd "$(dirname "$0")" && pwd)"
fi

# Sobe até 3 níveis procurando por BOOT.md
DIR="$CURRENT_DIR"
for i in {1..3}; do
    if [ -f "$DIR/BOOT.md" ]; then
        export FCP_REF_ROOT="$DIR"
        export FCP_REF_CONTEXT="${FCP_REF_CONTEXT:-$FCP_REF_ROOT}"
        return 0 2>/dev/null || exit 0
    fi
    # Tenta ler do cache se existir no diretório atual ou pai
    if [ -f "$DIR/.fcp_ref_root" ]; then
        export FCP_REF_ROOT="$(cat "$DIR/.fcp_ref_root")"
        if [ -f "$FCP_REF_ROOT/BOOT.md" ]; then
            export FCP_REF_CONTEXT="${FCP_REF_CONTEXT:-$FCP_REF_ROOT}"
            return 0 2>/dev/null || exit 0
        fi
    fi
    DIR="$(dirname "$DIR")"
done

echo "AVISO: Não foi possível detectar FCP_REF_ROOT subindo de $CURRENT_DIR" >&2

