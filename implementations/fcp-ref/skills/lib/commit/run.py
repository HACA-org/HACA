#!/usr/bin/env python3
"""commit — git checkpoint within workspace_focus.

commit always requires workspace_focus to be inside workspace/ — regardless of
profile. The entity may read/write its own structure via file_reader/file_writer
(Evolve), but git history of the entity root is not managed by the CPE.
"""

from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path


def main() -> None:
    req = json.loads(sys.stdin.read())
    params = req.get("params", {})
    entity_root = Path(req.get("entity_root", ".")).resolve()
    workspace = entity_root / "workspace"

    path_param = str(params.get("path", "")).strip()
    message = str(params.get("message", "checkpoint")).strip()
    remote = bool(params.get("remote", False))

    if not path_param:
        print(json.dumps({"error": "missing required param: path"}))
        sys.exit(1)

    # validate workspace_focus
    focus_file = entity_root / "state" / "workspace_focus.json"
    if not focus_file.exists():
        print(json.dumps({"error": "workspace_focus not set"}))
        sys.exit(1)

    focus = json.loads(focus_file.read_text(encoding="utf-8"))
    focus_path = Path(str(focus.get("path", ""))).resolve()

    # commit is always restricted to workspace/ — even in Evolve
    try:
        focus_path.relative_to(workspace)
    except ValueError:
        print(json.dumps({"error": "commit requires workspace_focus inside workspace/"}))
        sys.exit(1)

    target = (focus_path / path_param).resolve()
    try:
        target.relative_to(focus_path)
    except ValueError:
        print(json.dumps({"error": f"path outside workspace_focus: {path_param}"}))
        sys.exit(1)

    # git add + commit
    def run(cmd: list[str]) -> tuple[int, str, str]:
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(focus_path))
        return r.returncode, r.stdout.strip(), r.stderr.strip()

    code, _, err = run(["git", "add", str(target)])
    if code != 0:
        print(json.dumps({"error": f"git add failed: {err}"}))
        sys.exit(1)

    code, out, err = run(["git", "commit", "-m", message])
    if code != 0:
        print(json.dumps({"error": f"git commit failed: {err}"}))
        sys.exit(1)

    result: dict[str, object] = {"status": "ok", "commit": out}

    if remote:
        code, out, err = run(["git", "push", "origin"])
        if code != 0:
            print(json.dumps({"error": f"git push failed: {err}"}))
            sys.exit(1)
        result["pushed"] = True

    print(json.dumps(result))


main()
