#!/usr/bin/env bash
# skill_audit — validate a skill's manifest, executable, and index consistency
set -euo pipefail

SKILL_NAME="${FCP_PARAM_SKILL:?FCP_PARAM_SKILL is required}"
ENTITY_ROOT="${FCP_ENTITY_ROOT:?FCP_ENTITY_ROOT is required}"

SKILLS_DIR="$ENTITY_ROOT/skills"
INDEX_PATH="$SKILLS_DIR/index.json"

# Locate skill directory (regular or lib/)
skill_dir=""
if [ -d "$SKILLS_DIR/$SKILL_NAME" ]; then
    skill_dir="$SKILLS_DIR/$SKILL_NAME"
elif [ -d "$SKILLS_DIR/lib/$SKILL_NAME" ]; then
    skill_dir="$SKILLS_DIR/lib/$SKILL_NAME"
else
    echo "error: skill not found: $SKILL_NAME" >&2
    exit 1
fi

errors=()

# 1. Manifest exists and has required 'name' field
manifest_path="$skill_dir/manifest.json"
if [ ! -f "$manifest_path" ]; then
    errors+=("manifest missing: $manifest_path")
else
    name=$(python3 -c "
import json, sys
try:
    d = json.load(open(sys.argv[1]))
    print(d.get('name', ''))
except Exception:
    print('')
" "$manifest_path")
    if [ -z "$name" ]; then
        errors+=("manifest missing 'name' field or malformed JSON")
    fi
fi

# 2. Executable permissions (if present)
for exe_name in execute.sh execute.py; do
    if [ -f "$skill_dir/$exe_name" ]; then
        if [ ! -x "$skill_dir/$exe_name" ]; then
            errors+=("executable not executable: $exe_name")
        fi
        break
    fi
done

# 3. Skill present in skills/index.json
if [ -f "$INDEX_PATH" ]; then
    in_index=$(python3 -c "
import json, sys
try:
    idx = json.load(open(sys.argv[1]))
    names = [s.get('name', '') for s in idx.get('skills', [])]
    print('yes' if sys.argv[2] in names else 'no')
except Exception:
    print('no')
" "$INDEX_PATH" "$SKILL_NAME")
    if [ "$in_index" = "no" ]; then
        errors+=("skill not present in skills/index.json")
    fi
else
    errors+=("skills/index.json not found")
fi

if [ ${#errors[@]} -eq 0 ]; then
    echo "OK: $SKILL_NAME — manifest valid, index consistent"
else
    printf 'AUDIT FAILED: %s\n' "$SKILL_NAME"
    for err in "${errors[@]}"; do
        printf '  - %s\n' "$err"
    done
    exit 1
fi
