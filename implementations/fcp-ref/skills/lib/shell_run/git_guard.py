"""
git_guard — architectural boundary enforcement for git commands in shell_run.

Called by run.py before executing any command where base_cmd == "git".
Ensures git never operates on a repo rooted at entity_root/ or its ancestors.

Three violations detected:
  1. repo root IS entity_root      → would affect entity internals
  2. repo root is ANCESTOR of entity_root → would affect entity internals
  3. repo root is OUTSIDE workspace_focus → git init required in workspace_focus first
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def check(entity_root: Path, workspace_focus: Path) -> dict[str, str] | None:
    """Validate git repo root against architectural boundaries.

    Runs 'git rev-parse --show-toplevel' with cwd=workspace_focus to discover
    which repo git would operate on. Returns an error dict if the operation
    should be blocked, or None if safe to proceed.

    Args:
        entity_root:     Resolved absolute path to entity root directory.
        workspace_focus: Resolved absolute path to current workspace_focus.

    Returns:
        None if safe, or {"error": "<reason>"} if blocked.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(workspace_focus),
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        # git not available or timed out — let the command fail naturally
        return None

    if result.returncode != 0:
        # No repo found in hierarchy — let git report the error naturally
        return None

    repo_root = Path(result.stdout.strip()).resolve()

    if repo_root == entity_root:
        return {
            "error": (
                f"git: repo root is entity_root ({repo_root}) — "
                "operation would affect entity internals"
            )
        }

    if entity_root.is_relative_to(repo_root):
        return {
            "error": (
                f"git: repo root ({repo_root}) is an ancestor of entity_root — "
                "operation would affect entity internals"
            )
        }

    if not repo_root.is_relative_to(workspace_focus):
        return {
            "error": (
                f"git: repo root ({repo_root}) is outside workspace_focus ({workspace_focus}) — "
                "git init required in workspace_focus first"
            )
        }

    return None
