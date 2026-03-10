# sys_telemetry — Monitora o uso de tokens e recursos da sessão.
# Implementação para logar e consultar uso de tokens (Input/Output/Model).

set -euo pipefail

[ -z "${FCP_REF_ROOT:-}" ] && source "$(dirname "$0")/../load_agent_root.sh"
source "$FCP_REF_ROOT/skills/lib/acp.sh"
source "$FCP_REF_ROOT/skills/lib/params.sh"

ACTION=$(param_get "action" "status")
MODEL=$(param_get "model" "unknown")
INPUT_TOKENS=$(param_get "input_tokens" "0")
OUTPUT_TOKENS=$(param_get "output_tokens" "0")

compute_usage() {
    # Lê os últimos eventos do tipo TELEMETRY do log da sessão
    python3 << PYEOF
import json, os
session_path = os.path.join(os.environ['FCP_REF_ROOT'], 'memory', 'session.jsonl')
total_in = 0
total_out = 0
models = {}

if os.path.exists(session_path):
    with open(session_path, 'r') as f:
        for line in f:
            try:
                env = json.loads(line)
                if env.get('type') == 'TELEMETRY':
                    data = json.loads(env.get('data', '{}'))
                    ti = int(data.get('input_tokens', 0))
                    to = int(data.get('output_tokens', 0))
                    m  = data.get('model', 'unknown')
                    total_in += ti
                    total_out += to
                    models[m] = models.get(m, 0) + ti + to
            except: continue

print(f"--- [TELEMETRY STATUS] ---")
print(f"Total Input:  {total_in} tokens")
print(f"Total Output: {total_out} tokens")
print(f"Total:        {total_in + total_out} tokens")
if models:
    print(f"Usage by model:")
    for m, count in models.items():
        print(f"  - {m}: {count} tokens")
PYEOF
}

case "$ACTION" in
    "log_usage")
        DATA=$(python3 -c "import json,sys; print(json.dumps({'model':sys.argv[1],'input_tokens':int(sys.argv[2]),'output_tokens':int(sys.argv[3]),'ts':sys.argv[4]}))" \
               "$MODEL" "$INPUT_TOKENS" "$OUTPUT_TOKENS" "$(date -u +"%Y-%m-%dT%H:%M:%SZ")")
        acp_write "sil" "TELEMETRY" "$DATA" >/dev/null
        echo "[sys_telemetry] Usage logged: ${INPUT_TOKENS} in / ${OUTPUT_TOKENS} out (${MODEL})"
        ;;
    "status")
        compute_usage
        ;;
    *)
        echo "[sys_telemetry] ERROR: unknown action '$ACTION'" >&2
        exit 1
        ;;
esac
