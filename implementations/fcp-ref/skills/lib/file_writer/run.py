#!/usr/bin/env python3
"""file_writer — write, append, delete, move, or copy files within workspace_focus.

ops:
  write  (default) — create or overwrite a file (atomic via .tmp)
  append           — append content to a file (create if absent)
  delete           — remove a file or empty directory
  move             — move/rename a file or directory (dest must be within workspace_focus)
  copy             — copy a file (dest must be within workspace_focus)
"""

from __future__ import annotations
import json
import os
import shutil
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

    op = str(params.get("op", "write")).strip()

    target, err = _resolve(boundary, path_param)
    if err:
        print(json.dumps({"error": err}))
        sys.exit(1)

    # --- write (default) ---
    if op == "write":
        content = params.get("content", "")
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_text(str(content), encoding="utf-8")
        os.replace(tmp, target)
        print(json.dumps({"status": "ok", "op": "write", "path": path_param}))

    # --- append ---
    elif op == "append":
        content = params.get("content", "")
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as f:
            f.write(str(content))
        print(json.dumps({"status": "ok", "op": "append", "path": path_param}))

    # --- delete ---
    elif op == "delete":
        if not target.exists():
            print(json.dumps({"error": f"not found: {path_param}"}))
            sys.exit(1)
        if target.is_dir():
            target.rmdir()  # only removes empty dirs — intentional
        else:
            target.unlink()
        print(json.dumps({"status": "ok", "op": "delete", "path": path_param}))

    # --- move ---
    elif op == "move":
        dest_param = str(params.get("dest", "")).strip()
        if not dest_param:
            print(json.dumps({"error": "missing required param: dest"}))
            sys.exit(1)
        dest, err = _resolve(boundary, dest_param)
        if err:
            print(json.dumps({"error": err}))
            sys.exit(1)
        if not target.exists():
            print(json.dumps({"error": f"not found: {path_param}"}))
            sys.exit(1)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(target), str(dest))
        print(json.dumps({"status": "ok", "op": "move", "from": path_param, "to": dest_param}))

    # --- copy ---
    elif op == "copy":
        dest_param = str(params.get("dest", "")).strip()
        if not dest_param:
            print(json.dumps({"error": "missing required param: dest"}))
            sys.exit(1)
        dest, err = _resolve(boundary, dest_param)
        if err:
            print(json.dumps({"error": err}))
            sys.exit(1)
        if not target.exists():
            print(json.dumps({"error": f"not found: {path_param}"}))
            sys.exit(1)
        if target.is_dir():
            print(json.dumps({"error": "copy of directories not supported — copy individual files"}))
            sys.exit(1)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(target), str(dest))
        print(json.dumps({"status": "ok", "op": "copy", "from": path_param, "to": dest_param}))

    else:
        print(json.dumps({"error": f"unknown op: {op!r} — must be one of: write, append, delete, move, copy"}))
        sys.exit(1)


main()
