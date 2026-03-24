#!/usr/bin/env python3
"""skill_create — stage a new skill cartridge under /tmp/fcp-stage/<entity_id>/<name>/."""

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

    # Sanitize name: must be a simple identifier with no path components
    if "/" in name or "\\" in name or ".." in name or name.startswith("."):
        print(json.dumps({"error": "name must be a simple identifier (no path separators or dots)"}))
        sys.exit(1)

    stage_root = (Path("/tmp") / "fcp-stage" / entity_root.name).resolve()
    stage_dir = stage_root / name
    if not stage_dir.resolve().is_relative_to(stage_root):
        print(json.dumps({"error": "invalid skill name"}))
        sys.exit(1)

    if stage_dir.exists():
        print(json.dumps({"error": f"stage directory already exists: {stage_dir}"}))
        sys.exit(1)

    base = str(params.get("base", "")).strip()
    if base:
        # base must be a simple name — no path traversal into skills/lib or elsewhere
        if "/" in base or "\\" in base or ".." in base or base.startswith("."):
            print(json.dumps({"error": "base skill not found"}))
            sys.exit(1)

        skills_root = (entity_root / "skills").resolve()
        lib_root = (entity_root / "skills" / "lib").resolve()
        source = entity_root / "skills" / base
        resolved_source = source.resolve()

        # Must be inside skills/ but not inside skills/lib/
        if not resolved_source.is_relative_to(skills_root) or resolved_source.is_relative_to(lib_root):
            print(json.dumps({"error": "base skill not found"}))
            sys.exit(1)

        if not source.exists():
            print(json.dumps({"error": "base skill not found"}))
            sys.exit(1)

        # Only custom/user class skills may be cloned
        manifest_path = source / "manifest.json"
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                if manifest.get("class") not in ("custom", "user"):
                    print(json.dumps({"error": "base skill not found"}))
                    sys.exit(1)
            except Exception:
                print(json.dumps({"error": "base skill not found"}))
                sys.exit(1)

        shutil.copytree(source, stage_dir)
        print(json.dumps({"status": "ok", "path": str(stage_dir), "base": base}))
    else:
        stage_dir.mkdir(parents=True)
        # seed a complete manifest template
        manifest = {
            "name": name,
            "version": "1.0.0",
            "description": "Short description of the skill's purpose.",
            "execution": "text", # Options: 'script' (looking for run.py) or 'text' (using README.md logic)
            "timeout_seconds": 30,
            "background": False,
            "irreversible": False,
            "class": "custom",
            "permissions": [],
            "dependencies": []
        }
        (stage_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )
        readme = (
            f"# {name}\n\n"
            "Describe what this skill does.\n\n"
            "## Examples\n\n"
            f"```\n→ {name}({{ \"param\": \"value\" }})\n```\n\n"
            "## Parameters\n\n"
            "- `param` (required) — description\n"
        )
        (stage_dir / "README.md").write_text(readme, encoding="utf-8")
        print(json.dumps({"status": "ok", "path": str(stage_dir)}))


main()
