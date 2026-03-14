"""Tests for Sleep Cycle stages."""

import json
import shutil
import unittest

from fcp_core import sleep as sleep_mod
from fcp_core.store import Layout, atomic_write, append_jsonl, read_jsonl
from tests.helpers import make_layout


class TestStage1Consolidation(unittest.TestCase):
    def setUp(self) -> None:
        self.layout, self.tmp = make_layout()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def test_no_closure_is_noop(self) -> None:
        sleep_mod._stage1_consolidation(self.layout)
        # session store should remain empty
        records = read_jsonl(self.layout.session_store)
        self.assertEqual(records, [])

    def test_closure_processed(self) -> None:
        atomic_write(self.layout.session_handoff, {})
        atomic_write(self.layout.pending_closure, {
            "type": "closure_payload",
            "consolidation": "summary text",
            "working_memory": [
                {"priority": 1, "path": "memory/session-handoff.json"}
            ],
            "session_handoff": {"pending_tasks": [], "next_steps": "done"},
            "promotion": [],
        })
        sleep_mod._stage1_consolidation(self.layout)
        self.assertFalse(self.layout.pending_closure.exists())
        records = read_jsonl(self.layout.session_store)
        self.assertGreater(len(records), 0)


class TestStage2GC(unittest.TestCase):
    def setUp(self) -> None:
        self.layout, self.tmp = make_layout()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def test_stale_symlinks_cleaned(self) -> None:
        # create a stale symlink
        stale = self.layout.active_context_dir / "stale.md"
        stale.symlink_to(self.layout.root / "memory" / "semantic" / "nonexistent.md")
        self.assertTrue(stale.is_symlink())
        sleep_mod._stage2_gc(self.layout)
        self.assertFalse(stale.exists())

    def test_valid_symlink_preserved(self) -> None:
        from fcp_core.mil import write_semantic
        write_semantic(self.layout, "keep", "content")
        link = self.layout.active_context_dir / "keep.md"
        link.symlink_to(self.layout.semantic_dir / "keep.md")
        sleep_mod._stage2_gc(self.layout)
        self.assertTrue(link.is_symlink() and link.exists())


class TestSleepComplete(unittest.TestCase):
    def setUp(self) -> None:
        self.layout, self.tmp = make_layout()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def test_sleep_complete_written(self) -> None:
        sleep_mod._write_sleep_complete(self.layout)
        content = self.layout.integrity_log.read_text(encoding="utf-8")
        self.assertIn("SLEEP_COMPLETE", content)

    def test_session_token_removed(self) -> None:
        atomic_write(self.layout.session_token, {"issued_at": 0})
        self.assertTrue(self.layout.session_token.exists())
        sleep_mod._remove_session_token(self.layout)
        self.assertFalse(self.layout.session_token.exists())


class TestSessionRotation(unittest.TestCase):
    def setUp(self) -> None:
        self.layout, self.tmp = make_layout()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def test_rotation_below_threshold(self) -> None:
        self.layout.session_store.write_text("small", encoding="utf-8")
        sleep_mod._rotate_session_store(self.layout)
        # not rotated — still exists at original path
        self.assertTrue(self.layout.session_store.exists())
        self.assertEqual(self.layout.session_store.read_text(encoding="utf-8"), "small")

    def test_rotation_above_threshold(self) -> None:
        # write baseline with tiny threshold
        from fcp_core.store import atomic_write as aw
        import json
        baseline = json.loads(self.layout.baseline.read_text(encoding="utf-8"))
        baseline["session_store"]["rotation_threshold_bytes"] = 10
        aw(self.layout.baseline, baseline)
        self.layout.session_store.write_text("x" * 20, encoding="utf-8")
        sleep_mod._rotate_session_store(self.layout)
        # session.jsonl should now be empty (fresh)
        self.assertTrue(self.layout.session_store.exists())
        self.assertEqual(self.layout.session_store.read_text(encoding="utf-8"), "")
        # episodic dir should have a rotated file
        import datetime
        year = str(datetime.date.today().year)
        rotated = list((self.layout.episodic_dir / year).glob("*.jsonl"))
        self.assertGreater(len(rotated), 0)


if __name__ == "__main__":
    unittest.main()
