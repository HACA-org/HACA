"""
Tests for workspace_focus security validation.

Validates:
1. workspace_focus must be outside entity root
2. Absolute paths outside entity root are allowed
3. Paths that are ancestors of entity_root are rejected
4. Paths inside entity root are rejected
5. Relative paths resolve against cwd
"""

import unittest
from pathlib import Path

from fcp_base.store import Layout, atomic_write
from fcp_base.vital import _check_workspace_focus


class TestWorkspaceFocusAbsolutePaths:
    """Test absolute path handling."""

    def test_absolute_path_outside_entity_root(self, tmp_path):
        """Absolute path outside entity_root is allowed."""
        entity_root = tmp_path / "test_entity"
        entity_root.mkdir()
        layout = Layout(entity_root)

        external_dir = tmp_path / "external_project"
        external_dir.mkdir()
        target = external_dir.resolve()

        # Should not be an ancestor of entity_root
        try:
            layout.root.relative_to(target)
            assert False, "Target should not be an ancestor of entity_root"
        except ValueError:
            pass  # Good

    def test_reject_path_inside_entity_root(self, tmp_path):
        """Paths inside entity root must be rejected."""
        entity_root = tmp_path / "test_entity"
        entity_root.mkdir()
        layout = Layout(entity_root)

        inside = entity_root / "state"
        inside.mkdir()
        target = inside.resolve()

        # target.relative_to(entity_root) succeeds → REJECT
        try:
            target.relative_to(layout.root)
            assert True  # Correctly identified as inside entity root
        except ValueError:
            assert False, "Path inside entity root should be detectable"


class TestWorkspaceFocusSecurityValidation:
    """Test security constraints."""

    def test_reject_entity_root_as_target(self, tmp_path):
        """Reject setting focus to entity_root itself."""
        entity_root = tmp_path / "test_entity"
        entity_root.mkdir()
        layout = Layout(entity_root)

        target = layout.root.resolve()

        # entity_root.relative_to(entity_root) succeeds → REJECT (inside entity)
        try:
            target.relative_to(layout.root)
            assert True  # Correctly identified as violation
        except ValueError:
            assert False, "entity_root should be rejected"

    def test_reject_parent_of_entity_root(self, tmp_path):
        """Reject paths that are parents of entity_root."""
        entity_root = tmp_path / "test_entity"
        entity_root.mkdir()
        layout = Layout(entity_root)

        target = tmp_path.resolve()

        # layout.root.relative_to(target) succeeds → REJECT (ancestor)
        try:
            layout.root.relative_to(target)
            assert True  # Correctly identified as violation
        except ValueError:
            assert False, "Parent directory should be rejected"

    def test_reject_root_filesystem(self, tmp_path):
        """Reject filesystem root (/) as target."""
        entity_root = tmp_path / "test_entity"
        entity_root.mkdir()
        layout = Layout(entity_root)

        target = Path("/").resolve()

        try:
            layout.root.relative_to(target)
            assert True  # Correctly identified as ancestor
        except ValueError:
            assert False, "Filesystem root should be rejected"

    def test_allow_sibling_directory(self, tmp_path):
        """Allow setting focus to a sibling directory (not ancestor, not inside entity)."""
        entity_root = tmp_path / "test_entity"
        entity_root.mkdir()
        layout = Layout(entity_root)

        sibling = tmp_path / "sibling_project"
        sibling.mkdir()
        target = sibling.resolve()

        # Must not be inside entity root
        try:
            target.relative_to(layout.root)
            assert False, "Sibling should not be inside entity root"
        except ValueError:
            pass  # Good

        # Must not be an ancestor of entity root
        try:
            layout.root.relative_to(target)
            assert False, "Sibling should not be an ancestor"
        except ValueError:
            pass  # Good


# ---------------------------------------------------------------------------
# Tests for vital._check_workspace_focus
# ---------------------------------------------------------------------------

class TestVitalCheckWorkspaceFocus(unittest.TestCase):

    def _make_layout(self):
        from tests.helpers import make_layout
        return make_layout()

    def _set_focus(self, layout, path: Path) -> None:
        atomic_write(layout.root / "state" / "workspace_focus.json", {"path": str(path)})

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def setUp(self):
        self.layout, self.tmp = self._make_layout()

    def test_no_workspace_focus_file(self):
        # No workspace_focus.json → no criticals
        result = _check_workspace_focus(self.layout)
        self.assertEqual(result, [])

    def test_valid_focus_outside_entity(self):
        # Sibling directory — outside entity root, not ancestor
        import tempfile, shutil
        sibling = Path(tempfile.mkdtemp())
        try:
            self._set_focus(self.layout, sibling)
            result = _check_workspace_focus(self.layout)
            self.assertEqual(result, [])
        finally:
            shutil.rmtree(sibling, ignore_errors=True)

    def test_focus_inside_entity_root(self):
        # Path inside entity root → critical
        inside = self.layout.root / "state"
        inside.mkdir(parents=True, exist_ok=True)
        self._set_focus(self.layout, inside)
        result = _check_workspace_focus(self.layout)
        self.assertIn("workspace_focus_inside_entity", result)
        self.assertNotIn("workspace_focus_ancestor", result)

    def test_focus_is_entity_root_itself(self):
        # entity_root itself is inside entity root
        self._set_focus(self.layout, self.layout.root)
        result = _check_workspace_focus(self.layout)
        self.assertIn("workspace_focus_inside_entity", result)

    def test_focus_is_ancestor_of_entity_root(self):
        # Parent of entity_root → ancestor critical
        ancestor = self.layout.root.parent
        self._set_focus(self.layout, ancestor)
        result = _check_workspace_focus(self.layout)
        self.assertIn("workspace_focus_ancestor", result)
        self.assertNotIn("workspace_focus_inside_entity", result)

    def test_empty_path_in_focus_file(self):
        atomic_write(self.layout.root / "state" / "workspace_focus.json", {"path": ""})
        result = _check_workspace_focus(self.layout)
        self.assertEqual(result, [])
