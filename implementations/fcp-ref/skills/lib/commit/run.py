#!/usr/bin/env python3
"""commit — git operations within workspace_focus.

commit provides safe git operations (init, add, commit, status, log, branch, checkout)
within a workspace_focus directory. The entity cannot access the main entity repository.

Supported commands:
  - init: Initialize a new git repository in workspace_focus
  - add: Stage files for commit
  - commit: Create a commit
  - status: Show repository status
  - log: View commit history
  - diff: Show changes
  - branch: List/create branches
  - checkout: Switch branches
  - config: Set local git config (user.name, user.email)
  - push: Push to origin (requires confirmation in message)
"""

from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str], cwd: str) -> tuple[int, str, str]:
    """Run a shell command and return (returncode, stdout, stderr)."""
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def is_safe_commit_path(target_path: Path, entity_root: Path) -> bool:
    """Validate that target_path is safe for git operations.

    Rules:
    1. Inside workspace/ is safe
    2. Inside entity root but not in workspace is denied
    3. Outside entity root but not a parent is safe
    4. Parent of entity root is denied
    """
    workspace = entity_root / "workspace"

    # Rule 1: Inside workspace/
    try:
        target_path.relative_to(workspace)
        return True
    except ValueError:
        pass

    # Rule 2: If inside entity root but not in workspace -> DENY
    try:
        target_path.relative_to(entity_root)
        return False
    except ValueError:
        pass

    # Rule 3: If outside, ensure it is NOT a parent of entity_root
    if entity_root.is_relative_to(target_path):
        return False

    return True


def get_repo_root(cwd: str) -> str | None:
    """Get git repository root directory. Returns None if not a git repo."""
    code, toplevel, _ = run(["git", "rev-parse", "--show-toplevel"], cwd)
    return toplevel if code == 0 else None


def validate_focus(entity_root: Path) -> Path:
    """Load and validate workspace_focus. Raises error if invalid."""
    focus_file = entity_root / "state" / "workspace_focus.json"
    if not focus_file.exists():
        print(json.dumps({"error": "workspace_focus not set"}))
        sys.exit(1)

    focus = json.loads(focus_file.read_text(encoding="utf-8"))
    focus_path = Path(str(focus.get("path", ""))).resolve()

    if not is_safe_commit_path(focus_path, entity_root):
        print(json.dumps({"error": "commit path rejected: must be inside workspace/ or strictly outside the entity root (parents prohibited)"}))
        sys.exit(1)

    return focus_path


def cmd_init(focus_path: Path, entity_root: Path) -> None:
    """Initialize a git repository in workspace_focus."""
    repo_root = get_repo_root(str(focus_path))

    if repo_root:
        repo_root_path = Path(repo_root).resolve()
        if repo_root_path == entity_root or entity_root in repo_root_path.parents:
            print(json.dumps({"error": "git repository already exists at entity root"}))
            sys.exit(1)
        else:
            print(json.dumps({"status": "already_initialized", "repo_root": repo_root}))
            return

    code, out, err = run(["git", "init"], str(focus_path))
    if code != 0:
        print(json.dumps({"error": f"git init failed: {err}"}))
        sys.exit(1)

    # Set default user config
    run(["git", "config", "--local", "user.name", "HACA Entity"], str(focus_path))
    run(["git", "config", "--local", "user.email", "entity@haca.local"], str(focus_path))

    print(json.dumps({"status": "ok", "message": out}))


def cmd_add(focus_path: Path, entity_root: Path, path_param: str) -> None:
    """Stage files for commit."""
    if not path_param:
        print(json.dumps({"error": "missing required param: path"}))
        sys.exit(1)

    repo_root = get_repo_root(str(focus_path))
    if not repo_root:
        print(json.dumps({"error": "not a git repository — run 'init' first"}))
        sys.exit(1)

    target = (focus_path / path_param).resolve()
    try:
        target.relative_to(focus_path)
    except ValueError:
        print(json.dumps({"error": f"path outside workspace_focus: {path_param}"}))
        sys.exit(1)

    code, out, err = run(["git", "add", str(target)], str(repo_root))
    if code != 0:
        print(json.dumps({"error": f"git add failed: {err}"}))
        sys.exit(1)

    print(json.dumps({"status": "ok", "message": out if out else "staged"}))


def cmd_commit(focus_path: Path, entity_root: Path, message: str) -> None:
    """Create a commit."""
    if not message:
        message = "checkpoint"

    repo_root = get_repo_root(str(focus_path))
    if not repo_root:
        print(json.dumps({"error": "not a git repository — run 'init' first"}))
        sys.exit(1)

    code, out, err = run(["git", "commit", "-m", message], str(repo_root))
    if code != 0:
        print(json.dumps({"error": f"git commit failed: {err}"}))
        sys.exit(1)

    print(json.dumps({"status": "ok", "commit": out}))


def cmd_status(focus_path: Path) -> None:
    """Show repository status."""
    repo_root = get_repo_root(str(focus_path))
    if not repo_root:
        print(json.dumps({"error": "not a git repository"}))
        sys.exit(1)

    code, out, err = run(["git", "status", "--porcelain"], str(repo_root))
    if code != 0:
        print(json.dumps({"error": f"git status failed: {err}"}))
        sys.exit(1)

    lines = out.split('\n') if out else []
    print(json.dumps({"status": "ok", "changes": lines}))


def cmd_log(focus_path: Path, limit: int = 10) -> None:
    """View commit history."""
    repo_root = get_repo_root(str(focus_path))
    if not repo_root:
        print(json.dumps({"error": "not a git repository"}))
        sys.exit(1)

    code, out, err = run(["git", "log", f"--oneline", f"-{limit}"], str(repo_root))
    if code != 0:
        print(json.dumps({"error": f"git log failed: {err}"}))
        sys.exit(1)

    commits = [line for line in out.split('\n') if line.strip()]
    print(json.dumps({"status": "ok", "commits": commits}))


def cmd_diff(focus_path: Path, path_param: str = "") -> None:
    """Show changes."""
    repo_root = get_repo_root(str(focus_path))
    if not repo_root:
        print(json.dumps({"error": "not a git repository"}))
        sys.exit(1)

    cmd = ["git", "diff"]
    if path_param:
        target = (focus_path / path_param).resolve()
        try:
            target.relative_to(focus_path)
            cmd.append(str(target))
        except ValueError:
            print(json.dumps({"error": f"path outside workspace_focus: {path_param}"}))
            sys.exit(1)

    code, out, err = run(cmd, str(repo_root))
    if code != 0:
        print(json.dumps({"error": f"git diff failed: {err}"}))
        sys.exit(1)

    print(json.dumps({"status": "ok", "diff": out}))


def cmd_branch(focus_path: Path, action: str, name: str = "") -> None:
    """List or create branches."""
    repo_root = get_repo_root(str(focus_path))
    if not repo_root:
        print(json.dumps({"error": "not a git repository"}))
        sys.exit(1)

    if action == "list":
        code, out, err = run(["git", "branch", "-a"], str(repo_root))
        if code != 0:
            print(json.dumps({"error": f"git branch failed: {err}"}))
            sys.exit(1)
        branches = [line.strip() for line in out.split('\n') if line.strip()]
        print(json.dumps({"status": "ok", "branches": branches}))

    elif action == "create":
        if not name:
            print(json.dumps({"error": "branch name required"}))
            sys.exit(1)
        code, out, err = run(["git", "branch", name], str(repo_root))
        if code != 0:
            print(json.dumps({"error": f"git branch creation failed: {err}"}))
            sys.exit(1)
        print(json.dumps({"status": "ok", "message": f"branch '{name}' created"}))

    else:
        print(json.dumps({"error": f"unknown branch action: {action}"}))
        sys.exit(1)


def cmd_checkout(focus_path: Path, branch: str) -> None:
    """Switch branches."""
    if not branch:
        print(json.dumps({"error": "branch name required"}))
        sys.exit(1)

    repo_root = get_repo_root(str(focus_path))
    if not repo_root:
        print(json.dumps({"error": "not a git repository"}))
        sys.exit(1)

    code, out, err = run(["git", "checkout", branch], str(repo_root))
    if code != 0:
        print(json.dumps({"error": f"git checkout failed: {err}"}))
        sys.exit(1)

    print(json.dumps({"status": "ok", "message": out}))


def cmd_config(focus_path: Path, key: str, value: str) -> None:
    """Set local git config."""
    repo_root = get_repo_root(str(focus_path))
    if not repo_root:
        print(json.dumps({"error": "not a git repository — run 'init' first"}))
        sys.exit(1)

    # Only allow safe config keys
    allowed_keys = {"user.name", "user.email"}
    if key not in allowed_keys:
        print(json.dumps({"error": f"config key not allowed: {key}"}))
        sys.exit(1)

    code, out, err = run(["git", "config", "--local", key, value], str(repo_root))
    if code != 0:
        print(json.dumps({"error": f"git config failed: {err}"}))
        sys.exit(1)

    print(json.dumps({"status": "ok", "message": f"{key} set to '{value}'"}))


def cmd_push(focus_path: Path, force_confirm: bool = False) -> None:
    """Push to origin (requires confirmation)."""
    if not force_confirm:
        print(json.dumps({"error": "push requires confirmation: pass force_confirm=true"}))
        sys.exit(1)

    repo_root = get_repo_root(str(focus_path))
    if not repo_root:
        print(json.dumps({"error": "not a git repository"}))
        sys.exit(1)

    code, out, err = run(["git", "push", "origin"], str(repo_root))
    if code != 0:
        print(json.dumps({"error": f"git push failed: {err}"}))
        sys.exit(1)

    print(json.dumps({"status": "ok", "pushed": True, "message": out}))


def main() -> None:
    req = json.loads(sys.stdin.read())
    params = req.get("params", {})
    entity_root = Path(req.get("entity_root", ".")).resolve()

    cmd = str(params.get("command", "commit")).strip().lower()

    # Commands that don't require workspace_focus
    if cmd == "init":
        # For init, allow direct path parameter or use workspace_focus
        path_param = str(params.get("path", "")).strip()
        if path_param:
            target = Path(path_param).resolve()
            if not is_safe_commit_path(target, entity_root):
                print(json.dumps({"error": "path rejected: must be inside workspace/ or strictly outside entity root"}))
                sys.exit(1)
            cmd_init(target, entity_root)
        else:
            focus_path = validate_focus(entity_root)
            cmd_init(focus_path, entity_root)
        return

    # All other commands require workspace_focus
    focus_path = validate_focus(entity_root)

    if cmd == "add":
        path_param = str(params.get("path", "")).strip()
        cmd_add(focus_path, entity_root, path_param)

    elif cmd == "commit":
        message = str(params.get("message", "checkpoint")).strip()
        cmd_commit(focus_path, entity_root, message)

    elif cmd == "status":
        cmd_status(focus_path)

    elif cmd == "log":
        limit = int(params.get("limit", 10))
        cmd_log(focus_path, limit)

    elif cmd == "diff":
        path_param = str(params.get("path", "")).strip()
        cmd_diff(focus_path, path_param)

    elif cmd == "branch":
        action = str(params.get("action", "list")).strip().lower()
        name = str(params.get("name", "")).strip()
        cmd_branch(focus_path, action, name)

    elif cmd == "checkout":
        branch = str(params.get("branch", "")).strip()
        cmd_checkout(focus_path, branch)

    elif cmd == "config":
        key = str(params.get("key", "")).strip()
        value = str(params.get("value", "")).strip()
        cmd_config(focus_path, key, value)

    elif cmd == "push":
        force_confirm = bool(params.get("force_confirm", False))
        cmd_push(focus_path, force_confirm)

    else:
        print(json.dumps({"error": f"unknown command: {cmd}"}))
        sys.exit(1)


main()
