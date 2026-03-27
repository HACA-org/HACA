"""Tests for the First Activation Protocol."""

import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

from fcp_base import fap
from fcp_base.store import Layout, read_json
from tests.helpers import make_layout


def _patch_enroll(name: str = "Alice", email: str = "alice@example.com"):
    """Patch _enroll_operator to return fixed values without terminal I/O."""
    return patch("fcp_base.fap._enroll_operator", return_value=(name, email))


def _patch_channel():
    """Patch operator_channel_available to return (True, True)."""
    return patch("fcp_base.fap.operator_channel_available", return_value=(True, True))


class TestFAPStructuralValidation(unittest.TestCase):
    def setUp(self) -> None:
        self.layout, self.tmp = make_layout()
        # FAP requires imprint to NOT exist; make_layout creates it, so remove it.
        self.layout.imprint.unlink()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def test_missing_boot_md_raises(self) -> None:
        self.layout.boot_md.unlink()
        with _patch_enroll(), _patch_channel():
            with self.assertRaises(fap.FAPError) as cm:
                fap.run(self.layout)
        self.assertIn("boot.md", str(cm.exception))

    def test_missing_baseline_raises(self) -> None:
        self.layout.baseline.unlink()
        with _patch_enroll(), _patch_channel():
            with self.assertRaises(fap.FAPError) as cm:
                fap.run(self.layout)
        self.assertIn("baseline", str(cm.exception))

    def test_empty_persona_raises(self) -> None:
        for f in self.layout.persona_dir.iterdir():
            f.unlink()
        with _patch_enroll(), _patch_channel():
            with self.assertRaises(fap.FAPError) as cm:
                fap.run(self.layout)
        self.assertIn("persona", str(cm.exception))


class TestFAPChannelCheck(unittest.TestCase):
    def setUp(self) -> None:
        self.layout, self.tmp = make_layout()
        self.layout.imprint.unlink()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def test_no_notifications_dir_raises(self) -> None:
        with patch("fcp_base.fap.operator_channel_available", return_value=(False, True)):
            with _patch_enroll():
                with self.assertRaises(fap.FAPError) as cm:
                    fap.run(self.layout)
        self.assertIn("operator_notifications", str(cm.exception))

    def test_no_terminal_raises(self) -> None:
        with patch("fcp_base.fap.operator_channel_available", return_value=(True, False)):
            with _patch_enroll():
                with self.assertRaises(fap.FAPError) as cm:
                    fap.run(self.layout)
        self.assertIn("terminal", str(cm.exception))


class TestFAPSuccess(unittest.TestCase):
    def setUp(self) -> None:
        self.layout, self.tmp = make_layout()
        self.layout.imprint.unlink()
        # Also remove files that FAP writes so it starts clean
        for p in [self.layout.integrity_doc, self.layout.skills_index,
                  self.layout.integrity_chain, self.layout.session_token]:
            if p.exists():
                p.unlink()
        self.layout.integrity_chain.write_text("", encoding="utf-8")

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def _run(self) -> str:
        with _patch_enroll(), _patch_channel():
            return fap.run(self.layout)

    def test_returns_session_id(self) -> None:
        session_id = self._run()
        self.assertIsInstance(session_id, str)
        self.assertGreater(len(session_id), 0)

    def test_imprint_written(self) -> None:
        self._run()
        self.assertTrue(self.layout.imprint.exists())
        imprint = read_json(self.layout.imprint)
        self.assertIn("activated_at", imprint)
        self.assertIn("operator_bound", imprint)

    def test_operator_bound_captured(self) -> None:
        self._run()
        imprint = read_json(self.layout.imprint)
        ob = imprint["operator_bound"]
        self.assertEqual(ob["operator_name"], "Alice")
        self.assertEqual(ob["operator_email"], "alice@example.com")

    def test_integrity_doc_written(self) -> None:
        self._run()
        self.assertTrue(self.layout.integrity_doc.exists())
        doc = read_json(self.layout.integrity_doc)
        self.assertIn("files", doc)
        self.assertGreater(len(doc["files"]), 0)

    def test_integrity_chain_has_genesis(self) -> None:
        self._run()
        from fcp_base.store import read_jsonl
        chain = read_jsonl(self.layout.integrity_chain)
        self.assertGreater(len(chain), 0)
        genesis = chain[0]
        self.assertEqual(genesis.get("type"), "genesis")

    def test_session_token_written(self) -> None:
        self._run()
        self.assertTrue(self.layout.session_token.exists())

    def test_skills_index_written(self) -> None:
        self._run()
        self.assertTrue(self.layout.skills_index.exists())


class TestFAPRollback(unittest.TestCase):
    def setUp(self) -> None:
        self.layout, self.tmp = make_layout()
        self.layout.imprint.unlink()
        # Remove files that FAP writes
        for p in [self.layout.integrity_doc, self.layout.skills_index,
                  self.layout.integrity_chain, self.layout.session_token]:
            if p.exists():
                p.unlink()
        self.layout.integrity_chain.write_text("", encoding="utf-8")

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def test_rollback_on_enrollment_cancel(self) -> None:
        with _patch_channel():
            with patch("fcp_base.fap._enroll_operator",
                       side_effect=fap.FAPError("cancelled")):
                with self.assertRaises(fap.FAPError):
                    fap.run(self.layout)
        # imprint must NOT exist after rollback
        self.assertFalse(self.layout.imprint.exists())

    def test_rollback_cleans_written_files(self) -> None:
        # Force failure after skills_index is written (step 5)
        original_write_integrity_doc = fap.write_integrity_doc

        def _fail(*args, **kwargs):  # type: ignore[override]
            raise fap.FAPError("forced failure after skills_index")

        with _patch_enroll(), _patch_channel():
            with patch("fcp_base.fap.write_integrity_doc", side_effect=_fail):
                with self.assertRaises(fap.FAPError):
                    fap.run(self.layout)

        # skills_index was written then rolled back
        self.assertFalse(self.layout.skills_index.exists())
        self.assertFalse(self.layout.imprint.exists())


if __name__ == "__main__":
    unittest.main()
