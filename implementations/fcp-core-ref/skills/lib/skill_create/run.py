#!/usr/bin/env python3
"""skill_create — stage a new skill cartridge under workspace/stage/<name>/."""

from __future__ import annotations
import json
import shutil
import sys
from pathlib import Path


def main() -> None:
    req = json.loads(sys.stdin.read())
    params = req.get("params", {})
    entity_root = Path(req.get("entity_root", "."))

    name = str(params.get("name", "")).strip()
    if not name:
        print(json.dumps({"error": "missing required param: name"}))
        sys.exit(1)

    stage_dir = entity_root / "workspace" / "stage" / name
    if stage_dir.exists():
        print(json.dumps({"error": f"stage directory already exists: {stage_dir}"}))
        sys.exit(1)

    base = str(params.get("base", "")).strip()
    if base:
        source = entity_root / "skills" / base
        if not source.exists():
            print(json.dumps({"error": f"base skill not found: {base}"}))
            sys.exit(1)
        shutil.copytree(source, stage_dir)
        print(json.dumps({"status": "ok", "path": str(stage_dir), "base": base}))
    else:
        stage_dir.mkdir(parents=True)
        # seed a minimal manifest template
        manifest = {
            "name": name,
            "version": "1.0.0",
            "description": "",
            "timeout_seconds": 30,
            "background": False,
            "irreversible": False,
            "class": "custom",
            "permissions": []
        }
        (stage_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )
        (stage_dir / "run.py").write_text(
            '#!/usr/bin/env python3\nimport json, sys\n\n'
            'def main() -> None:\n'
            '    req = json.loads(sys.stdin.read())\n'
            '    params = req.get("params", {})\n'
            '    print(json.dumps({"status": "ok"}))\n\n'
            'main()\n',
            encoding="utf-8"
        )
        print(json.dumps({"status": "ok", "path": str(stage_dir)}))


main()
