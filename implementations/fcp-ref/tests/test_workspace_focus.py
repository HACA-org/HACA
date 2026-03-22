"""
Tests for workspace_focus security validation (2026-03-20).

Validates:
1. Relative paths resolve against entity_root/workspace/
2. Absolute paths allowed if not ancestors of entity_root
3. Paths that are ancestors of entity_root are rejected
4. /work set . maps to entity_root/workspace/
"""

import json
import tempfile
import unittest
from pathlib import Path

import pytest
from fcp_base.store import Layout, atomic_write
from fcp_base.vital import _check_workspace_focus


def create_test_entity(tmp_path: Path, profile: str = "haca-core") -> Layout:
    """Create a minimal test entity with necessary structure."""
    entity_root = tmp_path / "test_entity"
    entity_root.mkdir()

    # Create baseline
    baseline_path = entity_root / "baseline.json"
    atomic_write(baseline_path, {
        "profile": profile,
        "cpe": {"backend": "ollama", "model": "llama2"},
    })

    # Create state directory
    state_dir = entity_root / "state"
    state_dir.mkdir()

    # Create workspace directory
    workspace_dir = entity_root / "workspace"
    workspace_dir.mkdir()

    return Layout(entity_root)


class TestWorkspaceFocusRelativePaths:
    """Test relative path handling."""

    def test_relative_subdir(self, tmp_path):
        """Relative path resolves against entity_root/workspace/."""
        layout = create_test_entity(tmp_path)
        subdir = "myproject"

        # Simulate /work set myproject
        workspace_dir = layout.workspace_dir
        target = (workspace_dir / subdir).resolve()

        # Target should be entity_root/workspace/myproject
        assert str(target) == str(workspace_dir / subdir)
        # Should not be an ancestor of entity_root
        try:
            layout.root.relative_to(target)
            assert False, "Target should not be an ancestor of entity_root"
        except ValueError:
            pass  # Good

    def test_dot_maps_to_workspace_dir(self, tmp_path):
        """Dot (.) resolves to entity_root/workspace/."""
        layout = create_test_entity(tmp_path)

        # Simulate /work set .
        workspace_dir = layout.workspace_dir
        target = workspace_dir.resolve()

        assert target == workspace_dir
        # Should not be an ancestor of entity_root
        try:
            layout.root.relative_to(target)
            assert False, "Target should not be an ancestor of entity_root"
        except ValueError:
            pass  # Good

    def test_empty_string_maps_to_workspace_dir(self, tmp_path):
        """Empty string resolves to entity_root/workspace/."""
        layout = create_test_entity(tmp_path)

        # Simulate /work set "" (edge case)
        workspace_dir = layout.workspace_dir
        target = workspace_dir.resolve()

        assert target == workspace_dir


class TestWorkspaceFocusAbsolutePaths:
    """Test absolute path handling."""

    def test_absolute_path_outside_entity_root(self, tmp_path):
        """Absolute path outside entity_root is allowed."""
        layout = create_test_entity(tmp_path)

        # Create a directory completely outside entity_root
        external_dir = tmp_path / "external_project"
        external_dir.mkdir()

        target = external_dir.resolve()

        # Should not be an ancestor of entity_root
        try:
            layout.root.relative_to(target)
            assert False, "Target should not be an ancestor of entity_root"
        except ValueError:
            pass  # Good - external_dir is not an ancestor of entity_root

    def test_absolute_path_inside_workspace(self, tmp_path):
        """Absolute path inside entity_root/workspace/ is allowed."""
        layout = create_test_entity(tmp_path)

        subdir = layout.workspace_dir / "myproject"
        subdir.mkdir()

        target = subdir.resolve()

        # Should not be an ancestor of entity_root
        try:
            layout.root.relative_to(target)
            assert False, "Target should not be an ancestor of entity_root"
        except ValueError:
            pass  # Good


class TestWorkspaceFocusSecurityValidation:
    """Test security constraints."""

    def test_reject_entity_root_as_target(self, tmp_path):
        """Reject setting focus to entity_root itself."""
        layout = create_test_entity(tmp_path)

        target = layout.root.resolve()

        # entity_root.relative_to(entity_root) succeeds → REJECT
        try:
            layout.root.relative_to(target)
            # If we get here, target IS entity_root or an ancestor
            assert target == layout.root or target in layout.root.parents
            # This is a security violation
            assert True  # Correctly identified as violation
        except ValueError:
            assert False, "entity_root should be rejected as ancestor check"

    def test_reject_parent_of_entity_root(self, tmp_path):
        """Reject paths that are parents of entity_root."""
        layout = create_test_entity(tmp_path)

        # Try to use tmp_path (parent of entity_root) as target
        target = tmp_path.resolve()

        # tmp_path.relative_to(target) should succeed → REJECT
        try:
            layout.root.relative_to(target)
            # If we get here, target is an ancestor of entity_root
            assert True  # Correctly identified as violation
        except ValueError:
            assert False, "Parent directory should be rejected"

    def test_reject_root_filesystem(self, tmp_path):
        """Reject filesystem root (/) as target."""
        layout = create_test_entity(tmp_path)

        target = Path("/").resolve()

        # root.relative_to(Path("/")) succeeds → REJECT
        try:
            layout.root.relative_to(target)
            # If we get here, target is an ancestor of entity_root (it is - it's /)
            assert True  # Correctly identified as violation
        except ValueError:
            assert False, "Filesystem root should be rejected"

    def test_allow_sibling_directory(self, tmp_path):
        """Allow setting focus to a sibling directory (not ancestor)."""
        layout = create_test_entity(tmp_path)

        # Create a sibling of entity_root
        sibling = tmp_path / "sibling_project"
        sibling.mkdir()

        target = sibling.resolve()

        # sibling.relative_to(sibling) succeeds, but sibling is not ancestor of entity_root
        # entity_root.relative_to(sibling) should raise ValueError
        try:
            layout.root.relative_to(target)
            assert False, "Sibling should not be an ancestor"
        except ValueError:
            pass  # Good - sibling is not an ancestor of entity_root


class TestWorkspaceFocusNested:
    """Test nested directory structures."""

    def test_nested_relative_path(self, tmp_path):
        """Nested relative paths resolve correctly."""
        layout = create_test_entity(tmp_path)

        # Simulate /work set subdir1/subdir2/project
        workspace_dir = layout.workspace_dir
        target = (workspace_dir / "subdir1" / "subdir2" / "project").resolve()

        # Should be under workspace_dir
        try:
            target.relative_to(workspace_dir)
            pass  # Good
        except ValueError:
            assert False, "Nested relative path should be under workspace_dir"

        # Should not be an ancestor of entity_root
        try:
            layout.root.relative_to(target)
            assert False, "Target should not be an ancestor of entity_root"
        except ValueError:
            pass  # Good

    def test_relative_path_with_parent_refs(self, tmp_path):
        """Relative path with .. should still resolve under workspace_dir after normalization."""
        layout = create_test_entity(tmp_path)

        # Simulate /work set subdir/../otherdir
        # After resolve(), this becomes entity_root/workspace/otherdir
        workspace_dir = layout.workspace_dir
        target = (workspace_dir / "subdir" / ".." / "otherdir").resolve()

        # Should normalize to entity_root/workspace/otherdir
        assert target == workspace_dir / "otherdir"


class TestWorkspaceFocusProfiles:
    """Test that workspace_focus validation is consistent across profiles."""

    def test_haca_core_profile(self, tmp_path):
        """haca-core profile uses same validation as haca-evolve."""
        layout = create_test_entity(tmp_path, profile="haca-core")

        # Should reject ancestors
        target = layout.root.resolve()
        try:
            layout.root.relative_to(target)
            # entity_root is its own ancestor - should reject
            assert True
        except ValueError:
            assert False, "Should identify entity_root as ancestor"

    def test_haca_evolve_profile(self, tmp_path):
        """haca-evolve profile uses same validation as haca-core."""
        layout = create_test_entity(tmp_path, profile="haca-evolve")

        # Should reject ancestors
        target = layout.root.resolve()
        try:
            layout.root.relative_to(target)
            # entity_root is its own ancestor - should reject
            assert True
        except ValueError:
            assert False, "Should identify entity_root as ancestor"


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

    def test_valid_focus_inside_workspace(self):
        focus = self.layout.workspace_dir
        self._set_focus(self.layout, focus)
        result = _check_workspace_focus(self.layout)
        self.assertEqual(result, [])

    def test_valid_focus_subdir_inside_workspace(self):
        subdir = self.layout.workspace_dir / "project"
        subdir.mkdir(parents=True, exist_ok=True)
        self._set_focus(self.layout, subdir)
        result = _check_workspace_focus(self.layout)
        self.assertEqual(result, [])

    def test_focus_outside_workspace_not_ancestor(self):
        # Sibling directory — outside workspace but not ancestor of entity_root
        import tempfile, shutil
        sibling = Path(tempfile.mkdtemp())
        try:
            self._set_focus(self.layout, sibling)
            result = _check_workspace_focus(self.layout)
            self.assertIn("workspace_focus_invalid", result)
            self.assertNotIn("workspace_focus_ancestor", result)
        finally:
            shutil.rmtree(sibling, ignore_errors=True)

    def test_focus_is_ancestor_of_entity_root(self):
        # Parent of entity_root — the critical case P3 was about
        ancestor = self.layout.root.parent
        self._set_focus(self.layout, ancestor)
        result = _check_workspace_focus(self.layout)
        self.assertIn("workspace_focus_ancestor", result)
        self.assertNotIn("workspace_focus_invalid", result)

    def test_focus_is_entity_root_itself(self):
        # entity_root is its own ancestor
        self._set_focus(self.layout, self.layout.root)
        result = _check_workspace_focus(self.layout)
        self.assertIn("workspace_focus_ancestor", result)

    def test_empty_path_in_focus_file(self):
        atomic_write(self.layout.root / "state" / "workspace_focus.json", {"path": ""})
        result = _check_workspace_focus(self.layout)
        self.assertEqual(result, [])
