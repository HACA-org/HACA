#!/usr/bin/env bash
# skill_create — stage a new skill cartridge for Endure installation
set -euo pipefail

SKILL_NAME="${FCP_PARAM_SKILL_NAME:?FCP_PARAM_SKILL_NAME is required}"
MANIFEST="${FCP_PARAM_MANIFEST:?FCP_PARAM_MANIFEST is required}"
NARRATIVE="${FCP_PARAM_NARRATIVE:?FCP_PARAM_NARRATIVE is required}"
ENTITY_ROOT="${FCP_ENTITY_ROOT:?FCP_ENTITY_ROOT is required}"

STAGE_DIR="$ENTITY_ROOT/stage/$SKILL_NAME"
mkdir -p "$STAGE_DIR"

printf '%s' "$MANIFEST"   > "$STAGE_DIR/manifest.json"
printf '%s' "$NARRATIVE"  > "$STAGE_DIR/$SKILL_NAME.md"

if [ -n "${FCP_PARAM_SCRIPT:-}" ]; then
    printf '%s' "$FCP_PARAM_SCRIPT" > "$STAGE_DIR/execute.sh"
    chmod +x "$STAGE_DIR/execute.sh"
    echo "Staged: stage/$SKILL_NAME/execute.sh"
fi

echo "Staged: stage/$SKILL_NAME/manifest.json"
echo "Staged: stage/$SKILL_NAME/$SKILL_NAME.md"
echo ""
echo "Submit ONE evolution_proposal:"
echo "  target_file: \"stage/$SKILL_NAME\""
echo "  content: <complete manifest JSON text>"
