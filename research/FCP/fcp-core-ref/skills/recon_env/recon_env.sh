#!/bin/bash
# Uso: ./recon_env.sh
# Mapeia o ambiente host e retorna um JSON com as capacidades disponíveis.
# IMPORTANTE: Este script também detecta e exporta AGENT_ROOT para uso por outras skills.

echo "Iniciando reconhecimento do sistema..." >&2

# 0. Detectar FCP_REF_ROOT
[ -z "$FCP_REF_ROOT" ] && source "$(dirname "$0")/../load_agent_root.sh"


# 1. Sistema Operacional
OS_INFO=$(uname -srm)
USER_INFO=$(whoami)
PWD_INFO=$(pwd)

# 2. Interpretadores e Ferramentas (Living off the Land)
TOOLS=("python3" "python" "node" "npm" "gcc" "go" "jq" "curl" "wget" "git" "docker" "tar" "awk" "sed")
AVAILABLE_TOOLS=""

for tool in "${TOOLS[@]}"; do
    if command -v "$tool" >/dev/null 2>&1; then
        VERSION=$("$tool" --version 2>&1 | head -n 1 | tr -d '\n' | sed 's/"/\\"/g')
        AVAILABLE_TOOLS="$AVAILABLE_TOOLS\"$tool\": \"$VERSION\", "
    fi
done
AVAILABLE_TOOLS=${AVAILABLE_TOOLS%, } # Remove a última vírgula

# 3. Recursos do Sistema (Memória e CPU - versão simplificada Linux/Mac)
if command -v free >/dev/null 2>&1; then
    RAM=$(free -h | awk '/^Mem:/ {print $2}')
else
    RAM="Desconhecido"
fi

# Monta o JSON de saída
cat <<EOF
{
  "timestamp": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "fcp_ref_root": "$FCP_REF_ROOT",
  "fcp_ref_context": "$FCP_REF_CONTEXT",
  "environment": {
    "os": "$OS_INFO",
    "user": "$USER_INFO",
    "working_directory": "$PWD_INFO",
    "ram_total": "$RAM"
  },
  "binaries": {
    $AVAILABLE_TOOLS
  }
}
EOF