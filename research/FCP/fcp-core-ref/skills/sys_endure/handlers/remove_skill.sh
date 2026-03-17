#!/bin/bash
# sys_endure/handlers/remove_skill.sh
# Unregister a skill from index.json, unseal from integrity.json, delete directory.
# Requires --confirm to prevent accidental deletion.
#
# Required:
#   --name <name>   skill name to remove
#   --confirm       must be passed explicitly

set -euo pipefail

FCP_REF_ROOT="${FCP_REF_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"

NAME="" CONFIRM="false"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --name)    NAME="$2";    shift 2 ;;
        --confirm) CONFIRM="true"; shift ;;
        *) echo "[remove_skill] Unknown option: $1" >&2; shift ;;
    esac
done

if [ -z "$NAME" ]; then
    echo "[remove_skill] ERROR: --name is required" >&2
    exit 1
fi

if [ "$CONFIRM" != "true" ]; then
    echo "[remove_skill] ERROR: --confirm is required for destructive operations" >&2
    echo "[remove_skill]   Use: .endure remove skill --name $NAME --confirm"
    exit 1
fi

SKILL_DIR="$FCP_REF_ROOT/skills/$NAME"
if [ ! -d "$SKILL_DIR" ]; then
    echo "[remove_skill] ERROR: skill '$NAME' not found at $SKILL_DIR" >&2
    exit 1
fi

# ── Unregister from skills/index.json ────────────────────────────────────────
python3 - << PYEOF
import json, os

idx_path = "$FCP_REF_ROOT/skills/index.json"
with open(idx_path, 'r') as f:
    idx = json.load(f)

idx['skills'] = [s for s in idx['skills'] if s['name'] != "$NAME"]
idx['aliases'] = {k: v for k, v in idx.get('aliases', {}).items() if v != "$NAME"}

tmp = idx_path + '.tmp'
with open(tmp, 'w') as f:
    json.dump(idx, f, indent=4)
    f.write('\n')
    f.flush()
    os.fsync(f.fileno())
os.replace(tmp, idx_path)
print('[remove_skill] Unregistered from skills/index.json')
PYEOF

# ── Unseal from integrity.json ────────────────────────────────────────────────
python3 - << PYEOF
import json, os

integrity_path = "$FCP_REF_ROOT/state/integrity.json"
with open(integrity_path, 'r') as f:
    integrity = json.load(f)

sigs = integrity.get('signatures', {})
removed = [k for k in list(sigs.keys()) if k.startswith("skills/$NAME/")]
for k in removed:
    del sigs[k]
    print(f'[remove_skill] Unsealed: {k}')

integrity['signatures'] = sigs

tmp = integrity_path + '.tmp'
with open(tmp, 'w') as f:
    json.dump(integrity, f, indent=2)
    f.write('\n')
    f.flush()
    os.fsync(f.fileno())
os.replace(tmp, integrity_path)
PYEOF

# Recompute remaining hashes (index.json changed)
"$FCP_REF_ROOT/skills/sys_endure/handlers/seal.sh"

# ── Delete skill directory ────────────────────────────────────────────────────
rm -rf "$SKILL_DIR"
echo "[remove_skill] Deleted: skills/$NAME/"

echo ""
echo "[remove_skill] ✓ Skill '$NAME' removed."
echo "[remove_skill]   Run '.endure sync' to commit changes to git."
echo ""
echo "{\"status\":\"ok\",\"skill\":\"$NAME\",\"action\":\"removed\"}"
