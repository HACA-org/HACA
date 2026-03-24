"""Tests for git_guard — architectural boundary enforcement for git in shell_run."""

import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


# Import from the skill directory (not a package — load directly)
import importlib.util
_spec = importlib.util.spec_from_file_location(
    "git_guard",
    Path(__file__).parent.parent / "skills/lib/shell_run/git_guard.py",
)
git_guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(git_guard)


def _mock_git(repo_root: str | None):
    """Return a mock for subprocess.run that simulates git rev-parse output."""
    def _run(cmd, cwd, capture_output, text, timeout):
        class R:
            pass
        r = R()
        if repo_root is None:
            r.returncode = 128
            r.stdout = ""
            r.stderr = "not a git repository"
        else:
            r.returncode = 0
            r.stdout = repo_root + "\n"
            r.stderr = ""
        return r
    return _run


class TestGitGuard(unittest.TestCase):

    def setUp(self):
        self.tmp = TemporaryDirectory()
        base = Path(self.tmp.name)
        self.entity_root = base / "project" / ".entity"
        self.workspace = self.entity_root / "workspace"
        self.focus = self.workspace / "myproject"
        self.entity_root.mkdir(parents=True)
        self.focus.mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def _check(self, repo_root: str | None):
        with patch("subprocess.run", side_effect=_mock_git(repo_root)):
            return git_guard.check(self.entity_root, self.focus)

    def test_safe_repo_inside_workspace_focus(self):
        """Repo rooted inside workspace_focus — safe."""
        result = self._check(str(self.focus))
        self.assertIsNone(result)

    def test_safe_repo_subdir_of_focus(self):
        """Repo rooted in a subdir of workspace_focus — safe."""
        subdir = self.focus / "src"
        result = self._check(str(subdir))
        self.assertIsNone(result)

    def test_blocked_repo_is_entity_root(self):
        """Repo root IS entity_root — blocked."""
        result = self._check(str(self.entity_root))
        self.assertIsNotNone(result)
        self.assertIn("entity_root", result["error"])
        self.assertIn("entity internals", result["error"])

    def test_blocked_repo_is_ancestor_of_entity_root(self):
        """Repo root is ancestor of entity_root — blocked."""
        ancestor = self.entity_root.parent  # project/
        result = self._check(str(ancestor))
        self.assertIsNotNone(result)
        self.assertIn("ancestor", result["error"])
        self.assertIn("entity internals", result["error"])

    def test_blocked_repo_outside_workspace_focus(self):
        """Repo root is outside workspace_focus — blocked."""
        outside = self.entity_root / "state"  # inside entity root, not workspace_focus
        result = self._check(str(outside))
        self.assertIsNotNone(result)
        self.assertIn("outside workspace_focus", result["error"])
        self.assertIn("git init required", result["error"])

    def test_no_repo_found_passes(self):
        """No git repo found (returncode != 0) — passes, let git fail naturally."""
        result = self._check(None)
        self.assertIsNone(result)

    def test_git_unavailable_passes(self):
        """git binary unavailable — passes, let command fail naturally."""
        with patch("subprocess.run", side_effect=OSError("git not found")):
            result = git_guard.check(self.entity_root, self.focus)
        self.assertIsNone(result)

    def test_git_timeout_passes(self):
        """git times out — passes, let command fail naturally."""
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("git", 5)):
            result = git_guard.check(self.entity_root, self.focus)
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
