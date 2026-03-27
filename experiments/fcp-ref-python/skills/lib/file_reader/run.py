#!/usr/bin/env python3
"""file_reader — read, list, or search files within workspace_focus."""

from __future__ import annotations
import json
import re
import sys
from pathlib import Path


def _load_boundary(entity_root: Path) -> tuple[Path, str | None]:
    focus_file = entity_root / "state" / "workspace_focus.json"
    if not focus_file.exists():
        return Path(), "workspace_focus not set"
    try:
        focus = json.loads(focus_file.read_text(encoding="utf-8"))
        return Path(str(focus.get("path", ""))).resolve(), None
    except Exception as exc:
        return Path(), f"failed to load workspace_focus: {exc}"


def _resolve(boundary: Path, path_param: str) -> tuple[Path, str | None]:
    target = (boundary / path_param).resolve()
    try:
        target.relative_to(boundary)
    except ValueError:
        return Path(), f"path outside workspace_focus: {path_param}"
    return target, None


def main() -> None:
    req = json.loads(sys.stdin.read())
    params = req.get("params", {})
    entity_root = Path(req.get("entity_root", ".")).resolve()

    boundary, err = _load_boundary(entity_root)
    if err:
        print(json.dumps({"error": err}))
        sys.exit(1)

    path_param = str(params.get("path", "")).strip()
    if not path_param:
        print(json.dumps({"error": "missing required param: path"}))
        sys.exit(1)

    target, err = _resolve(boundary, path_param)
    if err:
        print(json.dumps({"error": err}))
        sys.exit(1)

    if not target.exists():
        print(json.dumps({"error": f"not found: {path_param}"}))
        sys.exit(1)

    # --- grep mode ---
    pattern = params.get("pattern")
    if pattern is not None:
        try:
            rx = re.compile(str(pattern))
        except re.error as exc:
            print(json.dumps({"error": f"invalid pattern: {exc}"}))
            sys.exit(1)

        matches: list[dict] = []
        files = sorted(target.rglob("*")) if target.is_dir() else [target]
        for f in files:
            if not f.is_file():
                continue
            try:
                for i, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                    if rx.search(line):
                        rel = str(f.relative_to(boundary))
                        matches.append({"file": rel, "line": i, "text": line})
            except Exception:
                continue
        print(json.dumps({"pattern": pattern, "path": path_param, "matches": matches}))
        return

    # --- directory listing ---
    if target.is_dir():
        entries = [p.name for p in sorted(target.iterdir())]
        print(json.dumps({"path": path_param, "type": "directory", "entries": entries}))
        return

    # --- file read with optional range ---
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
