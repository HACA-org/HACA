#!/usr/bin/env python3
"""file_reader — read a file within workspace/."""

from __future__ import annotations
import json
import sys
from pathlib import Path


def main() -> None:
    req = json.loads(sys.stdin.read())
    params = req.get("params", {})
    entity_root = Path(req.get("entity_root", ".")).resolve()
    workspace = entity_root / "workspace"

    path_param = str(params.get("path", "")).strip()
    if not path_param:
        print(json.dumps({"error": "missing required param: path"}))
        sys.exit(1)

    target = (workspace / path_param).resolve()
    try:
        target.relative_to(workspace)
    except ValueError:
        print(json.dumps({"error": f"path outside workspace: {path_param}"}))
        sys.exit(1)

    if not target.exists():
        print(json.dumps({"error": f"file not found: {path_param}"}))
        sys.exit(1)

    if target.is_dir():
        entries = [p.name for p in sorted(target.iterdir())]
        print(json.dumps({"path": path_param, "type": "directory", "entries": entries}))
        return

    content = target.read_text(encoding="utf-8", errors="replace")
    print(json.dumps({"path": path_param, "content": content}))


main()
