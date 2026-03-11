#!/bin/bash

# Carrega FCP_REF_ROOT se necessário
[ -z "$FCP_REF_ROOT" ] && source "$(dirname "$0")/load_agent_root.sh"

# Uso: ./snapshot_restore.sh <nome_do_arquivo_snapshot.tar.gz>

SNAPSHOT_FILE=$1
SNAPSHOT_PATH="$FCP_REF_ROOT/snapshots/${SNAPSHOT_FILE}"

if [ ! -f "$SNAPSHOT_PATH" ]; then
    echo "[ERRO] Arquivo de snapshot não encontrado: $SNAPSHOT_PATH"
    exit 1
fi

echo "ATENÇÃO: Restaurar um snapshot sobrescreverá a memória e skills atuais."
echo "Criando um backup de emergência do estado atual antes de restaurar..."
"$FCP_REF_ROOT/skills/snapshot_create.sh" "Backup de emergência pré-restore"

echo "Restaurando a mente a partir de $SNAPSHOT_FILE..."
# Extrai sobrescrevendo os arquivos atuais
tar -xzf "$SNAPSHOT_PATH" -C "$FCP_REF_ROOT"

if [ $? -eq 0 ]; then
    # Registra a restauração na memória
    "$FCP_REF_ROOT/skills/memory_store.sh" "episodic" "system,snapshot,restore" "Snapshot restaurado: $SNAPSHOT_FILE" "success"
    echo "[OK] Restauração concluída. O agente voltou no tempo."
else
    echo "[ERRO] Falha ao restaurar snapshot!"
    exit 1
fi