#!/bin/bash
# skills/owner_bind/owner_bind.sh — Operator Binding (First Boot)
# Establishes the human operator identity for this FCP instance.
# Writes memory/preferences/operator.json (atomic rename).
# Should only be called once — during FIRST_BOOT protocol.

[ -z "$FCP_REF_ROOT" ] && source "$(dirname "$0")/../load_agent_root.sh"
source "$FCP_REF_ROOT/skills/lib/params.sh"
source "$FCP_REF_ROOT/skills/lib/acp.sh"

PARAMS_JSON="${1:-}"
PARAMS=$(parse_params "$PARAMS_JSON" "name handle contact timezone")

NAME=$(echo "$PARAMS" | python3 -c "import json,sys; p=json.load(sys.stdin); print(p.get('name',''))")
HANDLE=$(echo "$PARAMS" | python3 -c "import json,sys; p=json.load(sys.stdin); print(p.get('handle',''))")
CONTACT=$(echo "$PARAMS" | python3 -c "import json,sys; p=json.load(sys.stdin); print(p.get('contact',''))")
TIMEZONE=$(echo "$PARAMS" | python3 -c "import json,sys; p=json.load(sys.stdin); print(p.get('timezone','UTC'))")

if [ -z "$NAME" ] || [ -z "$HANDLE" ]; then
    echo "[owner_bind] ERROR: 'name' and 'handle' are required." >&2
    exit 1
fi

PREFS_DIR="$FCP_REF_ROOT/memory/preferences"
OPERATOR_FILE="$PREFS_DIR/operator.json"

# Lifecycle guard: operator binding is immutable after FAP.
# If operator.json already exists, this skill must not overwrite it.
if [ -f "$OPERATOR_FILE" ]; then
    echo "[owner_bind] ERROR: Operator already bound. Use .endure for identity evolution." >&2
    exit 2
fi
OPERATOR_TMP="$PREFS_DIR/operator.json.tmp"
TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

mkdir -p "$PREFS_DIR"

python3 << PYEOF
import json, os

data = {
    "name":      "$NAME",
    "handle":    "$HANDLE",
    "contact":   "$CONTACT",
    "timezone":  "$TIMEZONE",
    "bound_at":  "$TS",
    "actor_id":  "supervisor"
}

tmp = "$OPERATOR_TMP"
final = "$OPERATOR_FILE"

with open(tmp, 'w') as f:
    json.dump(data, f, indent=2)
    f.flush()
    os.fsync(f.fileno())

os.replace(tmp, final)
print(f"[owner_bind] Operator bound: {data['name']} (@{data['handle']})")
PYEOF

# Log to session via ACP
acp_append_envelope \
    "el" \
    "$(acp_next_gseq)" \
    "$(uuidgen 2>/dev/null || python3 -c 'import uuid; print(uuid.uuid4())')" \
    "1" "true" "MSG" "$TS" \
    "{\"event\": \"owner_bound\", \"name\": \"$NAME\", \"handle\": \"$HANDLE\", \"timezone\": \"$TIMEZONE\"}" \
    "$FCP_REF_ROOT/memory/session.jsonl"
