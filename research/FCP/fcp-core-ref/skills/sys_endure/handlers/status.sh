#!/bin/bash
# sys_endure/handlers/status.sh
# Show which files tracked in integrity.json have changed since last seal.

set -euo pipefail

FCP_REF_ROOT="${FCP_REF_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"

python3 - << 'PYEOF'
import json, hashlib, os, sys

fcp_ref_root = os.environ['FCP_REF_ROOT']
integrity_path = os.path.join(fcp_ref_root, 'state', 'integrity.json')

with open(integrity_path, 'r') as f:
    integrity = json.load(f)

sigs = integrity.get('signatures', {})
clean, dirty, missing = [], [], []

for rel_path, expected in sorted(sigs.items()):
    abs_path = os.path.join(fcp_ref_root, rel_path)
    if not os.path.isfile(abs_path):
        missing.append(rel_path)
    else:
        with open(abs_path, 'rb') as f:
            actual = hashlib.sha256(f.read()).hexdigest()
        if actual == expected:
            clean.append(rel_path)
        else:
            dirty.append(rel_path)

print(f"\n{'='*60}")
print(f"  sys_endure status")
print(f"  {len(sigs)} files tracked in integrity.json")
print(f"{'='*60}")

if dirty:
    print(f"\n  ⚠  MODIFIED ({len(dirty)}) — not yet sealed:")
    for f in dirty:
        print(f"     {f}")
    print(f"\n  Run '.endure seal' to update hashes.")

if missing:
    print(f"\n  ✗  MISSING ({len(missing)}) — tracked but not found:")
    for f in missing:
        print(f"     {f}")

if not dirty and not missing:
    print(f"\n  ✓  All {len(clean)} tracked files match their sealed hashes.")

print()

if dirty or missing:
    print("  Next steps:")
    print("    .endure seal              — recompute hashes")
    print("    .endure sync              — commit to git")
    print("    .endure sync --remote     — commit + push")
PYEOF
