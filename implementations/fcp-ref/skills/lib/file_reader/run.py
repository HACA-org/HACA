#!/usr/bin/env python3
"""file_reader — read a file within workspace/ (Core) or entity_root/ (Evolve)."""

from __future__ import annotations
import json
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

    target = (boundary / path_param).resolve()
    try:
        target.relative_to(boundary)
    except ValueError:
        label = "entity root" if profile == "haca-evolve" else "workspace"
        print(json.dumps({"error": f"path outside {label}: {path_param}"}))
        sys.exit(1)

    if not target.exists():
        print(json.dumps({"error": f"file not found: {path_param}"}))
        sys.exit(1)

    if target.is_dir():
        entries = [p.name for p in sorted(target.iterdir())]
        print(json.dumps({"path": path_param, "type": "directory", "entries": entries}))
        return

    lines = target.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    total = len(lines)

    offset = params.get("offset")
    limit = params.get("limit")

    start = max(0, int(offset) - 1) if offset is not None else 0
    end = min(total, start + int(limit)) if limit is not None else total

    content = "".join(lines[start:end])
    result: dict = {"path": path_param, "content": content, "total_lines": total}
    if offset is not None or limit is not None:
        result["lines"] = f"{start + 1}-{end}"
    print(json.dumps(result))


main()
