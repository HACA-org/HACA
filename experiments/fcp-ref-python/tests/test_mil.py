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

    def test_recall_episodic_by_slug(self) -> None:
        """Recall episodic file by slug uses index lookup (O(1))."""
        mil.write_episodic(self.layout, "notes", "episodic content")
        # Path is just the slug name, index resolves it
        result = mil.memory_recall(self.layout, "", "notes")
        self.assertEqual(result["status"], "found")
        self.assertGreater(len(result["paths"]), 0)
        self.assertIn("episodic content", result["contents"][0]["content"])

    def test_recall_episodic_index_cached(self) -> None:
        """Episodic index prevents repeated glob scans."""
        mil.write_episodic(self.layout, "cached", "data")
        # First recall populates index
        result1 = mil.memory_recall(self.layout, "", "cached")
        self.assertEqual(result1["status"], "found")
        # Index file should exist
        index_file = self.layout.episodic_dir / ".episodic-index.json"
        self.assertTrue(index_file.exists())
        # Second recall uses index
        result2 = mil.memory_recall(self.layout, "", "cached")
        self.assertEqual(result2["status"], "found")


class TestEpisodicIndex(unittest.TestCase):
    def setUp(self) -> None:
        self.layout, self.tmp = make_layout()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def test_index_created_on_write(self) -> None:
        """write_episodic() creates and maintains index."""
        mil.write_episodic(self.layout, "test", "content")
        index_file = self.layout.episodic_dir / ".episodic-index.json"
        self.assertTrue(index_file.exists())
        index = json.loads(index_file.read_text())
        self.assertIn("test", index)
        self.assertGreater(len(index["test"]), 0)

    def test_index_multiple_slugs(self) -> None:
        """Index tracks multiple slugs."""
        mil.write_episodic(self.layout, "slug1", "content1")
        mil.write_episodic(self.layout, "slug2", "content2")
        index_file = self.layout.episodic_dir / ".episodic-index.json"
        index = json.loads(index_file.read_text())
        self.assertIn("slug1", index)
        self.assertIn("slug2", index)

    def test_index_overwrite_removes_old(self) -> None:
        """Overwriting episodic slug updates index."""
        import time
        path1 = mil.write_episodic(self.layout, "slug", "v1")
        time.sleep(0.01)  # Ensure different timestamp
        path2 = mil.write_episodic(self.layout, "slug", "v2", overwrite=True)
        index_file = self.layout.episodic_dir / ".episodic-index.json"
        index = json.loads(index_file.read_text())
        # Index should reflect the new file path
        self.assertIn("slug", index)
        # Old file should be gone
        self.assertFalse(path1.exists())
        self.assertTrue(path2.exists())

    def test_rebuild_episodic_index(self) -> None:
        """_rebuild_episodic_index() recovers from missing index."""
        mil.write_episodic(self.layout, "slug1", "c1")
        mil.write_episodic(self.layout, "slug2", "c2")
        # Delete index to simulate corruption
        index_file = self.layout.episodic_dir / ".episodic-index.json"
        index_file.unlink()
        # Rebuild
        index = mil._rebuild_episodic_index(self.layout)
        self.assertIn("slug1", index)
        self.assertIn("slug2", index)
        # Index file recreated
        self.assertTrue(index_file.exists())

    def test_clean_episodic_index(self) -> None:
        """clean_episodic_index() removes orphaned entries."""
        path1 = mil.write_episodic(self.layout, "orphan", "content")
        mil.write_episodic(self.layout, "valid", "content")
        # Delete the orphan file manually
        path1.unlink()
        # Clean
        mil.clean_episodic_index(self.layout)
        index_file = self.layout.episodic_dir / ".episodic-index.json"
        index = json.loads(index_file.read_text())
        # orphan should be removed, valid should remain
        self.assertNotIn("orphan", index)
        self.assertIn("valid", index)


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
