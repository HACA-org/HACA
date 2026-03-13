#!/usr/bin/env bash
# skill_create — stage a new skill cartridge for Endure installation
set -euo pipefail

SKILL_NAME="${FCP_PARAM_SKILL_NAME:?FCP_PARAM_SKILL_NAME is required}"
MANIFEST="${FCP_PARAM_MANIFEST:?FCP_PARAM_MANIFEST is required}"
NARRATIVE="${FCP_PARAM_NARRATIVE:?FCP_PARAM_NARRATIVE is required}"
ENTITY_ROOT="${FCP_ENTITY_ROOT:?FCP_ENTITY_ROOT is required}"

STAGE_DIR="$ENTITY_ROOT/workspace/stage/$SKILL_NAME"
mkdir -p "$STAGE_DIR"

printf '%s' "$MANIFEST"   > "$STAGE_DIR/manifest.json"
printf '%s' "$NARRATIVE"  > "$STAGE_DIR/$SKILL_NAME.md"

if [ -n "${FCP_PARAM_SCRIPT:-}" ]; then
    printf '%s' "$FCP_PARAM_SCRIPT" > "$STAGE_DIR/execute.sh"
    chmod +x "$STAGE_DIR/execute.sh"
    echo "Staged: workspace/stage/$SKILL_NAME/execute.sh"
fi

if [ -n "${FCP_PARAM_HOOKS:-}" ]; then
    python3 - <<'PYEOF'
import json, os, sys
hooks_json = os.environ.get("FCP_PARAM_HOOKS", "")
skill_name = os.environ["FCP_PARAM_SKILL_NAME"]
stage_dir  = os.path.join(os.environ["FCP_ENTITY_ROOT"], "workspace", "stage", skill_name, "hooks")
if not hooks_json:
    sys.exit(0)
try:
    hooks = json.loads(hooks_json)
except json.JSONDecodeError as e:
    print(f"Warning: hooks param is not valid JSON: {e}", file=sys.stderr)
    sys.exit(0)
os.makedirs(stage_dir, exist_ok=True)
for event, script in hooks.items():
    path = os.path.join(stage_dir, f"{event}.sh")
    with open(path, "w") as f:
        f.write(script)
    os.chmod(path, 0o755)
    print(f"Staged: workspace/stage/{skill_name}/hooks/{event}.sh")
PYEOF
fi

echo "Staged: workspace/stage/$SKILL_NAME/manifest.json"
echo "Staged: workspace/stage/$SKILL_NAME/$SKILL_NAME.md"
echo ""
echo "Submit ONE evolution_proposal:"
echo "  target_file: \"workspace/stage/$SKILL_NAME\""
echo "  content: <complete manifest JSON text>"
