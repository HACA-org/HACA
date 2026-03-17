#!/bin/bash
# skills/lib/acp.sh — ACP thin wrapper. Implementation in core/acp.py.
#
# Source this file before use:
#   source "$FCP_REF_ROOT/skills/lib/acp.sh"

_ACP_PY="${FCP_REF_ROOT}/core/acp.py"

acp_crc32() {
    python3 -c "import zlib,sys; print(format(zlib.crc32(sys.argv[1].encode())&0xFFFFFFFF,'08x'))" "$1"
}

acp_new_tx() {
    python3 -c "import uuid; print(str(uuid.uuid4()))"
}

acp_next_gseq() {
    # Not needed externally — gseq is managed internally by acp.py
    echo "1"
}

acp_write() {
    local actor="$1" type="$2" data="$3"
    local tx="${4:-}" seq="${5:-1}" eof="${6:-true}"
    if [ -n "$tx" ]; then
        python3 "$_ACP_PY" write "$actor" "$type" "$data" "$tx" "$seq" "$eof"
    else
        python3 "$_ACP_PY" write "$actor" "$type" "$data"
    fi
}

acp_write_presession() {
    local actor="$1" type="$2" data="$3"
    local tx="${4:-}" seq="${5:-1}" eof="${6:-true}"
    python3 - "$actor" "$type" "$data" <<'PYEOF'
import json, os, sys
from pathlib import Path
sys.path.insert(0, os.environ.get("FCP_REF_ROOT", ""))
from core.acp import write_presession
root = Path(os.environ.get("FCP_REF_ROOT", ""))
actor, typ, data = sys.argv[1], sys.argv[2], sys.argv[3]
try:
    p = write_presession(actor, typ, data, root)
    print(p)
except OverflowError:
    sys.exit(1)
PYEOF
}

acp_read_inbox() {
    local inbox_dir="$FCP_REF_ROOT/memory/inbox"
    [ -d "$inbox_dir" ] || return 0
    for f in "$inbox_dir"/*.msg; do
        [ -f "$f" ] || continue
        cat "$f"
    done
}

acp_read_session() {
    local limit="${1:-50}"
    local session_file="$FCP_REF_ROOT/memory/session.jsonl"
    [ -f "$session_file" ] || return 0
    tail -n "$limit" "$session_file" | tac
}
