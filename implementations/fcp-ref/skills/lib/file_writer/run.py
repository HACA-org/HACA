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

    try:
        profile = json.loads((entity_root / "state" / "baseline.json").read_text()).get("profile", "haca-core")
    except Exception:
        profile = "haca-core"
    boundary = entity_root if profile == "haca-evolve" else entity_root / "workspace"

    path_param = str(params.get("path", "")).strip()
    if not path_param:
        print(json.dumps({"error": "missing required param: path"}))
        sys.exit(1)

    content = params.get("content", "")

    target = (boundary / path_param).resolve()
    try:
        target.relative_to(boundary)
    except ValueError:
        label = "entity root" if profile == "haca-evolve" else "workspace"
        print(json.dumps({"error": f"path outside {label}: {path_param}"}))
        sys.exit(1)

    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(str(content), encoding="utf-8")
    os.replace(tmp, target)

    print(json.dumps({"status": "ok", "path": path_param}))


main()
