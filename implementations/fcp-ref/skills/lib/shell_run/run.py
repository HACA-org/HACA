#!/usr/bin/env python3
"""shell_run — execute an allowlisted shell command within workspace_focus.

Simple commands (allowlist): run with shell=False, cwd=focus_path.
  - Path arguments starting with '/' or containing '..' are rejected.

Composite commands (allowlist_composite): run with shell=True, cwd=focus_path.
  - Matched by exact command string against the 'command' field.
  - No path sanitization — operator explicitly approved the full command.
"""

from __future__ import annotations
import json
import shlex
import subprocess
import sys
from pathlib import Path


def main() -> None:
    req = json.loads(sys.stdin.read())
    params = req.get("params", {})
    entity_root = Path(req.get("entity_root", ".")).resolve()

    command = str(params.get("command", "")).strip()
    if not command:
        print(json.dumps({"error": "missing required param: command"}))
        sys.exit(1)

    # validate workspace_focus
    focus_file = entity_root / "state" / "workspace_focus.json"
    if not focus_file.exists():
        print(json.dumps({"error": "workspace_focus not set"}))
        sys.exit(1)

    focus = json.loads(focus_file.read_text(encoding="utf-8"))
    focus_path = Path(str(focus.get("path", ""))).resolve()

    # load allowlists from manifest
    manifest_path = entity_root / "skills" / "lib" / "shell_run" / "manifest.json"
    allowlist: list[str] = []
    allowlist_composite: list[dict] = []
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        allowlist = [str(a) for a in manifest.get("allowlist", [])]
        allowlist_composite = [
            e for e in manifest.get("allowlist_composite", [])
            if isinstance(e, dict) and "command" in e
        ]

    # --- Stage 1: check composite allowlist (exact match) ---
    composite_match = next(
        (e for e in allowlist_composite if e["command"] == command), None
    )
    if composite_match:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            cwd=str(focus_path),
        )
        print(json.dumps({
            "status": "ok" if result.returncode == 0 else "error",
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }))
        return

    # --- Stage 2: check simple allowlist (first token match) ---
    try:
        tokens: list[str] = list(shlex.split(command))
    except ValueError as exc:
        print(json.dumps({"error": f"invalid command syntax: {exc}"}))
        sys.exit(1)

    base_cmd = tokens[0] if tokens else ""
    if base_cmd not in allowlist:
        print(json.dumps({"error": f"command not in allowlist: {base_cmd!r}"}))
        sys.exit(1)

    # reject absolute paths and traversal in arguments
    args = tokens[1:]
    for token in args:
        if token.startswith("/") or ".." in token.split("/"):
            print(json.dumps({"error": f"path argument not permitted: {token!r}"}))
            sys.exit(1)

    result = subprocess.run(
        tokens,
        shell=False,
        capture_output=True,
        text=True,
        cwd=str(focus_path),
    )

    print(json.dumps({
        "status": "ok" if result.returncode == 0 else "error",
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }))


main()
