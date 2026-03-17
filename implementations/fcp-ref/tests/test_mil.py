"""Tests for MIL — Memory Interface Layer."""

import json
import os
import shutil
import unittest
from pathlib import Path

from fcp_base import mil
from fcp_base.store import Layout
from tests.helpers import make_layout


class TestWriteEpisodic(unittest.TestCase):
    def setUp(self) -> None:
        self.layout, self.tmp = make_layout()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def test_write_creates_file(self) -> None:
        path = mil.write_episodic(self.layout, "test-note", "hello episodic")
        self.assertTrue(path.exists())
        self.assertIn("test-note", path.name)
        self.assertEqual(path.read_text(encoding="utf-8"), "hello episodic")

    def test_key_format(self) -> None:
        path = mil.write_episodic(self.layout, "my-slug", "content")
        # filename should be <timestamp>-my-slug.md
        self.assertTrue(path.name.endswith("-my-slug.md"))


class TestWriteSemantic(unittest.TestCase):
    def setUp(self) -> None:
        self.layout, self.tmp = make_layout()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def test_write_and_read(self) -> None:
        mil.write_semantic(self.layout, "arch", "# Architecture\nkey facts")
        dest = self.layout.semantic_dir / "arch.md"
        self.assertTrue(dest.exists())
        self.assertIn("Architecture", dest.read_text(encoding="utf-8"))


class TestPromoteToSemantic(unittest.TestCase):
    def setUp(self) -> None:
        self.layout, self.tmp = make_layout()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def test_promote_existing_slug(self) -> None:
        mil.write_episodic(self.layout, "react-rules", "use hooks, not classes")
        result = mil.promote_to_semantic(self.layout, "react-rules")
        self.assertTrue(result)
        self.assertTrue((self.layout.semantic_dir / "react-rules.md").exists())

    def test_promote_missing_slug(self) -> None:
        result = mil.promote_to_semantic(self.layout, "nonexistent")
        self.assertFalse(result)


class TestMemoryRecall(unittest.TestCase):
    def setUp(self) -> None:
        self.layout, self.tmp = make_layout()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def test_recall_existing(self) -> None:
        mil.write_semantic(self.layout, "arch", "architecture notes")
        result = mil.memory_recall(self.layout, "arch", "memory/semantic/arch.md")
        self.assertEqual(result["status"], "found")
        self.assertIn("memory/semantic/arch.md", result["paths"])
        link = self.layout.active_context_dir / "arch.md"
        self.assertTrue(link.is_symlink())

    def test_recall_missing(self) -> None:
        result = mil.memory_recall(self.layout, "missing", "memory/semantic/missing.md")
        self.assertEqual(result["status"], "not_found")
        self.assertEqual(result["paths"], [])

    def test_recall_returns_contents(self) -> None:
        mil.write_semantic(self.layout, "x", "content")
        result = mil.memory_recall(self.layout, "q", "memory/semantic/x.md")
        self.assertEqual(result["status"], "found")
        self.assertEqual(len(result["contents"]), 1)
        self.assertEqual(result["contents"][0]["content"], "content")


class TestSeedActiveContext(unittest.TestCase):
    def setUp(self) -> None:
        self.layout, self.tmp = make_layout()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def test_seed_valid_entries(self) -> None:
        mil.write_semantic(self.layout, "base", "base content")
        from fcp_base.store import atomic_write
        atomic_write(self.layout.working_memory, {
            "entries": [{"priority": 1, "path": "memory/semantic/base.md"}]
        })
        skipped = mil.seed_active_context(self.layout)
        self.assertEqual(skipped, [])
        link = self.layout.active_context_dir / "base.md"
        self.assertTrue(link.is_symlink())

    def test_seed_missing_entries_skipped(self) -> None:
        from fcp_base.store import atomic_write
        atomic_write(self.layout.working_memory, {
            "entries": [{"priority": 1, "path": "memory/semantic/absent.md"}]
        })
        skipped = mil.seed_active_context(self.layout)
        self.assertIn("memory/semantic/absent.md", skipped)


class TestProcessClosure(unittest.TestCase):
    def setUp(self) -> None:
        self.layout, self.tmp = make_layout()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def test_absent_closure_is_noop(self) -> None:
        result = mil.process_closure(self.layout)
        self.assertFalse(result)

    def test_processes_closure_payload(self) -> None:
        mil.write_semantic(self.layout, "handoff", "next steps")
        payload = {
            "type": "closure_payload",
            "consolidation": "session summary",
            "working_memory": [
                {"priority": 1, "path": "memory/session-handoff.json"},
                {"priority": 2, "path": "memory/semantic/handoff.md"},
            ],
            "session_handoff": {
                "pending_tasks": ["task1"],
                "next_steps": "continue work",
            },
            "promotion": [],
        }
        # write session-handoff first so working_memory entry is valid
        from fcp_base.store import atomic_write
        atomic_write(self.layout.session_handoff, {})
        atomic_write(self.layout.pending_closure, payload)
        result = mil.process_closure(self.layout)
        self.assertTrue(result)
        self.assertFalse(self.layout.pending_closure.exists())
        self.assertTrue(self.layout.working_memory.exists())
        self.assertTrue(self.layout.session_handoff.exists())
        handoff = json.loads(self.layout.session_handoff.read_text())
        self.assertEqual(handoff.get("next_steps"), "continue work")


class TestSummarizeSession(unittest.TestCase):
    def setUp(self) -> None:
        self.layout, self.tmp = make_layout()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def test_summarize_retains_content(self) -> None:
        # write 10 lines
        for i in range(10):
            line = json.dumps({"seq": i, "data": f"line {i}"}) + "\n"
            with self.layout.session_store.open("a") as f:
                f.write(line)
        original_size = self.layout.session_store.stat().st_size
        mil.summarize_session(self.layout)
        new_size = self.layout.session_store.stat().st_size
        # result should be no larger than original
        self.assertLessEqual(new_size, original_size)
        # should start with boundary marker
        content = self.layout.session_store.read_text(encoding="utf-8")
        self.assertIn("session summarized", content)


if __name__ == "__main__":
    unittest.main()
