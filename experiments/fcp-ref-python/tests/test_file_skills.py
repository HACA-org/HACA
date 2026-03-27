"""Tests for file_reader and file_writer skills."""

from __future__ import annotations
import importlib.util
import json
import shutil
import sys
import unittest
from pathlib import Path

from tests.helpers import make_layout


# ---------------------------------------------------------------------------
# Helpers to invoke skills directly
# ---------------------------------------------------------------------------

_SKILLS_LIB = Path(__file__).parent.parent / "skills" / "lib"


def _run_skill(skill_name: str, entity_root: Path, params: dict) -> dict:
    """Load and execute a skill run.py directly, returning parsed JSON output."""
    skill_path = _SKILLS_LIB / skill_name / "run.py"
    spec = importlib.util.spec_from_file_location(f"skill_{skill_name}", skill_path)
    mod = importlib.util.module_from_spec(spec)

    import io
    from unittest.mock import patch

    stdin_data = json.dumps({"params": params, "entity_root": str(entity_root)})
    stdout_capture = io.StringIO()

    with patch("sys.stdin", io.StringIO(stdin_data)), \
         patch("sys.stdout", stdout_capture):
        try:
            spec.loader.exec_module(mod)
        except SystemExit:
            pass

    output = stdout_capture.getvalue().strip()
    return json.loads(output) if output else {}


def _set_focus(layout, path: Path) -> None:
    """Set workspace_focus to given path."""
    from fcp_base.store import atomic_write
    atomic_write(layout.root / "state" / "workspace_focus.json", {"path": str(path)})


# ---------------------------------------------------------------------------
# file_reader
# ---------------------------------------------------------------------------

class TestFileReaderRead(unittest.TestCase):

    def setUp(self):
        self.layout, self.tmp = make_layout()
        self.workspace = self.tmp / "workspace"
        _set_focus(self.layout, self.workspace)
        self.test_file = self.workspace / "hello.txt"
        self.test_file.write_text("line1\nline2\nline3\nline4\nline5\n", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_read_full_file(self):
        result = _run_skill("file_reader", self.tmp, {"path": "hello.txt"})
        self.assertIn("content", result)
        self.assertIn("line1", result["content"])
        self.assertEqual(result["total_lines"], 5)

    def test_read_with_offset_and_limit(self):
        result = _run_skill("file_reader", self.tmp, {"path": "hello.txt", "offset": 2, "limit": 2})
        self.assertIn("line2", result["content"])
        self.assertIn("line3", result["content"])
        self.assertNotIn("line1", result["content"])
        self.assertNotIn("line4", result["content"])
        self.assertEqual(result["lines"], "2-3")

    def test_read_missing_file(self):
        result = _run_skill("file_reader", self.tmp, {"path": "nonexistent.txt"})
        self.assertIn("error", result)

    def test_read_outside_boundary(self):
        result = _run_skill("file_reader", self.tmp, {"path": "../state/baseline.json"})
        self.assertIn("error", result)
        self.assertIn("outside", result["error"])

    def test_missing_path_param(self):
        result = _run_skill("file_reader", self.tmp, {})
        self.assertIn("error", result)

    def test_no_workspace_focus(self):
        (self.tmp / "state" / "workspace_focus.json").unlink()
        result = _run_skill("file_reader", self.tmp, {"path": "hello.txt"})
        self.assertIn("error", result)


class TestFileReaderDirectory(unittest.TestCase):

    def setUp(self):
        self.layout, self.tmp = make_layout()
        self.workspace = self.tmp / "workspace"
        _set_focus(self.layout, self.workspace)
        (self.workspace / "subdir").mkdir()
        (self.workspace / "subdir" / "a.txt").write_text("a", encoding="utf-8")
        (self.workspace / "subdir" / "b.txt").write_text("b", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_list_directory(self):
        result = _run_skill("file_reader", self.tmp, {"path": "subdir"})
        self.assertEqual(result["type"], "directory")
        self.assertIn("a.txt", result["entries"])
        self.assertIn("b.txt", result["entries"])

    def test_list_root_workspace(self):
        result = _run_skill("file_reader", self.tmp, {"path": "."})
        self.assertEqual(result["type"], "directory")
        self.assertIn("subdir", result["entries"])


class TestFileReaderGrep(unittest.TestCase):

    def setUp(self):
        self.layout, self.tmp = make_layout()
        self.workspace = self.tmp / "workspace"
        _set_focus(self.layout, self.workspace)
        (self.workspace / "src").mkdir()
        (self.workspace / "src" / "main.py").write_text(
            "def foo():\n    return 42\n\ndef bar():\n    return 'hello'\n",
            encoding="utf-8"
        )
        (self.workspace / "src" / "other.py").write_text(
            "# TODO: fix this\nx = foo()\n",
            encoding="utf-8"
        )

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_grep_file(self):
        result = _run_skill("file_reader", self.tmp, {"path": "src/main.py", "pattern": "def "})
        self.assertIn("matches", result)
        self.assertEqual(len(result["matches"]), 2)
        self.assertEqual(result["matches"][0]["line"], 1)

    def test_grep_directory_recursive(self):
        result = _run_skill("file_reader", self.tmp, {"path": "src", "pattern": "foo"})
        self.assertIn("matches", result)
        files = {m["file"] for m in result["matches"]}
        self.assertTrue(any("main.py" in f for f in files))
        self.assertTrue(any("other.py" in f for f in files))

    def test_grep_no_matches(self):
        result = _run_skill("file_reader", self.tmp, {"path": "src", "pattern": "ZZZNOTFOUND"})
        self.assertIn("matches", result)
        self.assertEqual(result["matches"], [])

    def test_grep_invalid_pattern(self):
        result = _run_skill("file_reader", self.tmp, {"path": "src/main.py", "pattern": "["})
        self.assertIn("error", result)

    def test_grep_includes_line_numbers(self):
        result = _run_skill("file_reader", self.tmp, {"path": "src/other.py", "pattern": "TODO"})
        self.assertEqual(result["matches"][0]["line"], 1)
        self.assertIn("TODO", result["matches"][0]["text"])


# ---------------------------------------------------------------------------
# file_writer
# ---------------------------------------------------------------------------

class TestFileWriterWrite(unittest.TestCase):

    def setUp(self):
        self.layout, self.tmp = make_layout()
        self.workspace = self.tmp / "workspace"
        _set_focus(self.layout, self.workspace)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_write_new_file(self):
        result = _run_skill("file_writer", self.tmp, {"path": "new.txt", "content": "hello"})
        self.assertEqual(result["status"], "ok")
        self.assertEqual((self.workspace / "new.txt").read_text(), "hello")

    def test_write_creates_parent_dirs(self):
        result = _run_skill("file_writer", self.tmp, {"path": "a/b/c.txt", "content": "deep"})
        self.assertEqual(result["status"], "ok")
        self.assertTrue((self.workspace / "a" / "b" / "c.txt").exists())

    def test_write_overwrites_existing(self):
        (self.workspace / "f.txt").write_text("old", encoding="utf-8")
        _run_skill("file_writer", self.tmp, {"path": "f.txt", "content": "new"})
        self.assertEqual((self.workspace / "f.txt").read_text(), "new")

    def test_write_outside_boundary_rejected(self):
        result = _run_skill("file_writer", self.tmp, {"path": "../state/evil.json", "content": "x"})
        self.assertIn("error", result)
        self.assertFalse((self.tmp / "state" / "evil.json").exists())


class TestFileWriterAppend(unittest.TestCase):

    def setUp(self):
        self.layout, self.tmp = make_layout()
        self.workspace = self.tmp / "workspace"
        _set_focus(self.layout, self.workspace)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_append_to_existing(self):
        (self.workspace / "log.txt").write_text("line1\n", encoding="utf-8")
        _run_skill("file_writer", self.tmp, {"op": "append", "path": "log.txt", "content": "line2\n"})
        self.assertEqual((self.workspace / "log.txt").read_text(), "line1\nline2\n")

    def test_append_creates_file(self):
        result = _run_skill("file_writer", self.tmp, {"op": "append", "path": "new.txt", "content": "hello"})
        self.assertEqual(result["status"], "ok")
        self.assertEqual((self.workspace / "new.txt").read_text(), "hello")


class TestFileWriterDelete(unittest.TestCase):

    def setUp(self):
        self.layout, self.tmp = make_layout()
        self.workspace = self.tmp / "workspace"
        _set_focus(self.layout, self.workspace)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_delete_file(self):
        (self.workspace / "del.txt").write_text("bye", encoding="utf-8")
        result = _run_skill("file_writer", self.tmp, {"op": "delete", "path": "del.txt"})
        self.assertEqual(result["status"], "ok")
        self.assertFalse((self.workspace / "del.txt").exists())

    def test_delete_empty_dir(self):
        (self.workspace / "emptydir").mkdir()
        result = _run_skill("file_writer", self.tmp, {"op": "delete", "path": "emptydir"})
        self.assertEqual(result["status"], "ok")
        self.assertFalse((self.workspace / "emptydir").exists())

    def test_delete_nonexistent(self):
        result = _run_skill("file_writer", self.tmp, {"op": "delete", "path": "ghost.txt"})
        self.assertIn("error", result)

    def test_delete_outside_boundary_rejected(self):
        result = _run_skill("file_writer", self.tmp, {"op": "delete", "path": "../state/baseline.json"})
        self.assertIn("error", result)
        self.assertTrue((self.tmp / "state" / "baseline.json").exists())


class TestFileWriterMove(unittest.TestCase):

    def setUp(self):
        self.layout, self.tmp = make_layout()
        self.workspace = self.tmp / "workspace"
        _set_focus(self.layout, self.workspace)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_move_file(self):
        (self.workspace / "src.txt").write_text("data", encoding="utf-8")
        result = _run_skill("file_writer", self.tmp, {"op": "move", "path": "src.txt", "dest": "dst.txt"})
        self.assertEqual(result["status"], "ok")
        self.assertFalse((self.workspace / "src.txt").exists())
        self.assertEqual((self.workspace / "dst.txt").read_text(), "data")

    def test_move_creates_dest_parent(self):
        (self.workspace / "f.txt").write_text("x", encoding="utf-8")
        result = _run_skill("file_writer", self.tmp, {"op": "move", "path": "f.txt", "dest": "sub/f.txt"})
        self.assertEqual(result["status"], "ok")
        self.assertTrue((self.workspace / "sub" / "f.txt").exists())

    def test_move_missing_dest_param(self):
        result = _run_skill("file_writer", self.tmp, {"op": "move", "path": "f.txt"})
        self.assertIn("error", result)

    def test_move_dest_outside_boundary_rejected(self):
        (self.workspace / "f.txt").write_text("x", encoding="utf-8")
        result = _run_skill("file_writer", self.tmp, {"op": "move", "path": "f.txt", "dest": "../evil.txt"})
        self.assertIn("error", result)
        self.assertTrue((self.workspace / "f.txt").exists())


class TestFileWriterCopy(unittest.TestCase):

    def setUp(self):
        self.layout, self.tmp = make_layout()
        self.workspace = self.tmp / "workspace"
        _set_focus(self.layout, self.workspace)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_copy_file(self):
        (self.workspace / "orig.txt").write_text("original", encoding="utf-8")
        result = _run_skill("file_writer", self.tmp, {"op": "copy", "path": "orig.txt", "dest": "copy.txt"})
        self.assertEqual(result["status"], "ok")
        self.assertTrue((self.workspace / "orig.txt").exists())
        self.assertEqual((self.workspace / "copy.txt").read_text(), "original")

    def test_copy_directory_rejected(self):
        (self.workspace / "mydir").mkdir()
        result = _run_skill("file_writer", self.tmp, {"op": "copy", "path": "mydir", "dest": "mydir2"})
        self.assertIn("error", result)

    def test_copy_missing_dest_param(self):
        result = _run_skill("file_writer", self.tmp, {"op": "copy", "path": "orig.txt"})
        self.assertIn("error", result)

    def test_copy_dest_outside_boundary_rejected(self):
        (self.workspace / "f.txt").write_text("x", encoding="utf-8")
        result = _run_skill("file_writer", self.tmp, {"op": "copy", "path": "f.txt", "dest": "../evil.txt"})
        self.assertIn("error", result)


class TestFileWriterUnknownOp(unittest.TestCase):

    def setUp(self):
        self.layout, self.tmp = make_layout()
        _set_focus(self.layout, self.tmp / "workspace")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_unknown_op(self):
        result = _run_skill("file_writer", self.tmp, {"op": "explode", "path": "f.txt"})
        self.assertIn("error", result)
        self.assertIn("unknown op", result["error"])
