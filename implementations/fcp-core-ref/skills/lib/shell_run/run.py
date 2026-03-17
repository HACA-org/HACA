#!/usr/bin/env python3
"""shell_run — execute an allowlisted shell command within workspace_focus."""

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

    # load allowlist from manifest
    manifest_path = entity_root / "skills" / "lib" / "shell_run" / "manifest.json"
    allowlist: list[str] = []
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        allowlist = [str(a) for a in manifest.get("allowlist", [])]

    # check command against allowlist (match on first token)
    tokens = shlex.split(command)
    base_cmd = tokens[0] if tokens else ""
    if base_cmd not in allowlist:
        print(json.dumps({"error": f"command not in allowlist: {base_cmd!r}"}))
        sys.exit(1)

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


main()
