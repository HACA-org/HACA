#!/bin/bash
# sys_endure/handlers/add_skill.sh
# Scaffold a new skill, register in skills/index.json, seal in integrity.json.
#
# Required:
#   --name <name>            skill name (snake_case)
#   --description <text>     what the skill does
# Optional:
#   --command <.alias>       .command alias (e.g. .myskill)
#   --script <path>          path to script in workspaces/ to promote (creates stub if omitted)
#   --capabilities <list>    comma-separated (default: filesystem_write)
#   --sandbox <type>         workspaces_only|fcp_root|none (default: workspaces_only)

set -euo pipefail

FCP_REF_ROOT="${FCP_REF_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"

NAME="" DESCRIPTION="" COMMAND="" SCRIPT_SRC="" CAPABILITIES="filesystem_write" SANDBOX="workspaces_only"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --name)         NAME="$2";         shift 2 ;;
        --description)  DESCRIPTION="$2";  shift 2 ;;
        --command)      COMMAND="$2";      shift 2 ;;
        --script)       SCRIPT_SRC="$2";   shift 2 ;;
        --capabilities) CAPABILITIES="$2"; shift 2 ;;
        --sandbox)      SANDBOX="$2";      shift 2 ;;
        *) echo "[add_skill] Unknown option: $1" >&2; shift ;;
    esac
done

# ── Validation ────────────────────────────────────────────────────────────────
if [ -z "$NAME" ] || [ -z "$DESCRIPTION" ]; then
    echo "[add_skill] ERROR: --name and --description are required" >&2
    exit 1
fi

if ! echo "$NAME" | grep -qE '^[a-z][a-z0-9_]*$'; then
    echo "[add_skill] ERROR: name must be snake_case (a-z, 0-9, _)" >&2
    exit 1
fi

SKILL_DIR="$FCP_REF_ROOT/skills/$NAME"
if [ -d "$SKILL_DIR" ]; then
    echo "[add_skill] ERROR: skill '$NAME' already exists" >&2
    exit 1
fi

# Check alias conflict
if [ -n "$COMMAND" ]; then
    existing=$(python3 -c "
import json, sys
idx = json.load(open('$FCP_REF_ROOT/skills/index.json'))
print(idx.get('aliases', {}).get('$COMMAND', ''))
" 2>/dev/null)
    if [ -n "$existing" ]; then
        echo "[add_skill] ERROR: alias '$COMMAND' already assigned to '$existing'" >&2
        exit 1
    fi
fi

# ── Create skill directory ────────────────────────────────────────────────────
mkdir -p "$SKILL_DIR"

# Write manifest.json
python3 - << PYEOF
import json, os

caps = [c.strip() for c in "$CAPABILITIES".split(',')]
manifest = {
    "name": "$NAME",
    "version": "1.0",
    "description": "$DESCRIPTION",
    "capabilities": caps,
    "security": {
        "sandbox": "$SANDBOX",
        "write_targets": ["workspaces/"] if "$SANDBOX" == "workspaces_only" else []
    },
    "params": {}
}
if "$COMMAND":
    manifest["command"] = "$COMMAND"

path = "$SKILL_DIR/manifest.json"
with open(path, 'w') as f:
    json.dump(manifest, f, indent=4)
    f.write('\n')
print(f'[add_skill] Created manifest: skills/$NAME/manifest.json')
PYEOF

# Write script (copy from workspaces/ or create stub)
SCRIPT_DEST="$SKILL_DIR/$NAME.sh"

if [ -n "$SCRIPT_SRC" ]; then
    ABS_SCRIPT="$FCP_REF_ROOT/$SCRIPT_SRC"
    if [ ! -f "$ABS_SCRIPT" ]; then
        echo "[add_skill] ERROR: script not found: $SCRIPT_SRC" >&2
        rm -rf "$SKILL_DIR"
        exit 1
    fi
    cp "$ABS_SCRIPT" "$SCRIPT_DEST"
    chmod +x "$SCRIPT_DEST"
    echo "[add_skill] Promoted: $SCRIPT_SRC → skills/$NAME/$NAME.sh"
else
    cat > "$SCRIPT_DEST" << STUB
#!/bin/bash
# $NAME — $DESCRIPTION
# Scaffolded by sys_endure add skill. Implement logic below.

set -euo pipefail

[ -z "\$FCP_REF_ROOT" ] && source "\$(dirname "\$0")/../load_agent_root.sh"
source "\$FCP_REF_ROOT/skills/lib/acp.sh"
source "\$FCP_REF_ROOT/skills/lib/params.sh"

# TODO: implement $NAME logic
echo "[$NAME] Not yet implemented" >&2
exit 1
STUB
    chmod +x "$SCRIPT_DEST"
    echo "[add_skill] Created stub: skills/$NAME/$NAME.sh"
fi

# ── Register in skills/index.json ─────────────────────────────────────────────
python3 - << PYEOF
import json, os

idx_path = "$FCP_REF_ROOT/skills/index.json"
with open(idx_path, 'r') as f:
    idx = json.load(f)

idx['skills'].append({
    "name": "$NAME",
    "authorized": True,
    "path": "skills/$NAME/"
})

if "$COMMAND":
    idx.setdefault('aliases', {})["$COMMAND"] = "$NAME"

tmp = idx_path + '.tmp'
with open(tmp, 'w') as f:
    json.dump(idx, f, indent=4)
    f.write('\n')
    f.flush()
    os.fsync(f.fileno())
os.replace(tmp, idx_path)
print('[add_skill] Registered in skills/index.json')
PYEOF

# ── Seal new files in integrity.json ──────────────────────────────────────────
"$FCP_REF_ROOT/skills/sys_endure/handlers/seal.sh" \
    --add "skills/$NAME/manifest.json" \
    --add "skills/$NAME/$NAME.sh"

echo ""
echo "[add_skill] ✓ Skill '$NAME' created."
[ -n "$COMMAND" ] && echo "[add_skill]   Alias: $COMMAND"
echo "[add_skill]   Path: skills/$NAME/"
echo "[add_skill]   Run '.endure sync' to commit changes to git."
echo ""
echo "{\"status\":\"ok\",\"skill\":\"$NAME\",\"path\":\"skills/$NAME/\"}"
