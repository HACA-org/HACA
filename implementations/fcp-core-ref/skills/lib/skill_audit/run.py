#!/usr/bin/env python3
"""skill_audit — validate a skill's manifest, executable, and index consistency."""

from __future__ import annotations
import json
import sys
from pathlib import Path

REQUIRED_MANIFEST_FIELDS = ["name", "version", "description", "timeout_seconds",
                             "background", "irreversible", "class"]


def main() -> None:
    req = json.loads(sys.stdin.read())
    params = req.get("params", {})
    entity_root = Path(req.get("entity_root", "."))

    name = str(params.get("name", "")).strip()
    if not name:
        print(json.dumps({"error": "missing required param: name"}))
        sys.exit(1)

    issues: list[str] = []

    # locate manifest
    manifest_path = entity_root / "skills" / name / "manifest.json"
    lib_path = entity_root / "skills" / "lib" / name / "manifest.json"
    if lib_path.exists():
        manifest_path = lib_path

    if not manifest_path.exists():
        issues.append(f"manifest not found: {manifest_path}")
        print(json.dumps({"skill": name, "valid": False, "issues": issues}))
        return

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        issues.append(f"manifest parse error: {exc}")
        print(json.dumps({"skill": name, "valid": False, "issues": issues}))
        return

    for field in REQUIRED_MANIFEST_FIELDS:
        if field not in manifest:
            issues.append(f"missing manifest field: {field}")

    if manifest.get("name") != name:
        issues.append(f"manifest name mismatch: {manifest.get('name')!r} != {name!r}")

    # check executable
    skill_dir = manifest_path.parent
    exe_found = any((skill_dir / f).exists() for f in ("run.py", "run.sh", "run"))
    if not exe_found:
        issues.append("no executable found (run.py / run.sh / run)")

    # check index entry
    index_path = entity_root / "skills" / "index.json"
    if index_path.exists():
        try:
            index = json.loads(index_path.read_text(encoding="utf-8"))
            names = [s.get("name") for s in index.get("skills", [])]
            if name not in names:
                issues.append("skill absent from skills/index.json")
        except Exception as exc:
            issues.append(f"index parse error: {exc}")
    else:
        issues.append("skills/index.json not found")

    print(json.dumps({"skill": name, "valid": len(issues) == 0, "issues": issues}))


main()
