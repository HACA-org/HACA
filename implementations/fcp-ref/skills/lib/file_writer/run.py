#!/usr/bin/env python3
"""file_writer — write a file within workspace/ (Core) or entity_root/ (Evolve)."""

from __future__ import annotations
import json
import os
import sys
from pathlib import Path


def main() -> None:
    req = json.loads(sys.stdin.read())
    params = req.get("params", {})
    entity_root = Path(req.get("entity_root", ".")).resolve()

    # validate and load workspace_focus
    focus_file = entity_root / "state" / "workspace_focus.json"
    if not focus_file.exists():
        print(json.dumps({"error": "workspace_focus not set"}))
        sys.exit(1)
    
    try:
        focus = json.loads(focus_file.read_text(encoding="utf-8"))
        boundary = Path(str(focus.get("path", ""))).resolve()
    except Exception as exc:
        print(json.dumps({"error": f"failed to load workspace_focus: {exc}"}))
        sys.exit(1)

    path_param = str(params.get("path", "")).strip()
    if not path_param:
        print(json.dumps({"error": "missing required param: path"}))
        sys.exit(1)

    content = params.get("content", "")

    target = (boundary / path_param).resolve()
    try:
        target.relative_to(boundary)
    except ValueError:
        print(json.dumps({"error": f"path outside workspace_focus: {path_param}"}))
        sys.exit(1)

    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(str(content), encoding="utf-8")
    os.replace(tmp, target)

    print(json.dumps({"status": "ok", "path": path_param}))


main()
