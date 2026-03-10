#!/bin/bash
# sys_endure/handlers/seal.sh
# Recompute SHA-256 hashes for all files tracked in state/integrity.json.
# Optionally start tracking new files with --add <relative_path>.
#
# Usage: seal.sh [--add <path>] [--add <path2>] ...

set -euo pipefail

FCP_REF_ROOT="${FCP_REF_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"

NEW_FILES=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --add) NEW_FILES+=("$2"); shift 2 ;;
        *)     shift ;;
    esac
done

python3 - "${NEW_FILES[@]}" << 'PYEOF'
import json, hashlib, os, sys

fcp_ref_root = os.environ['FCP_REF_ROOT']
integrity_path = os.path.join(fcp_ref_root, 'state', 'integrity.json')
new_files = sys.argv[1:]  # passed via shell array expansion

with open(integrity_path, 'r') as f:
    integrity = json.load(f)

sigs = integrity.get('signatures', {})

# Register new files (value will be computed below)
for rel_path in new_files:
    if rel_path not in sigs:
        sigs[rel_path] = ''
        print(f'[seal] Tracking new file: {rel_path}')

# Recompute all tracked hashes
for rel_path in sorted(sigs.keys()):
    abs_path = os.path.join(fcp_ref_root, rel_path)
    if os.path.isfile(abs_path):
        with open(abs_path, 'rb') as f:
            digest = hashlib.sha256(f.read()).hexdigest()
        sigs[rel_path] = digest
        print(f'[seal] {rel_path} → {digest[:16]}…')
    else:
        print(f'[seal] WARN: tracked file missing: {rel_path}', file=sys.stderr)

integrity['signatures'] = sigs

# Atomic write
tmp = integrity_path + '.tmp'
with open(tmp, 'w') as f:
    json.dump(integrity, f, indent=2)
    f.write('\n')
    f.flush()
    os.fsync(f.fileno())
os.replace(tmp, integrity_path)

print(f'[seal] Done. {len(sigs)} files tracked in integrity.json.')
PYEOF
