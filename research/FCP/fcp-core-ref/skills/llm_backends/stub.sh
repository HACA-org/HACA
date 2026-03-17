#!/bin/bash
# stub.sh - Fallback backend (sempre disponível, retorna vazio)
# Usado quando nenhum LLM está configurado

if [ "$1" = "--test" ]; then
    # Stub sempre está "disponível" como último recurso
    exit 0
fi

# Retorna vazio (sem consolidação)
exit 0
