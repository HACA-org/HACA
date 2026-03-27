"""Tests for the compliance checker."""

import json
import shutil
import unittest
from pathlib import Path

from fcp_base.compliance import (
    check_structure, check_integrity, check_chain,
    check_skills, check_session_token, run_all,
)
from fcp_base.store import Layout, atomic_write
from tests.helpers import make_layout


class TestCheckStructure(unittest.TestCase):
    def setUp(self) -> None:
        self.layout, self.tmp = make_layout()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def test_complete_structure_passes(self) -> None:
        findings = check_structure(self.layout)
        failed = [f for f in findings if not f.passed]
        self.assertEqual(failed, [], msg=str(failed))

    def test_missing_boot_md_fails(self) -> None:
        self.layout.boot_md.unlink()
        findings = check_structure(self.layout)
        failed = [f for f in findings if not f.passed]
        self.assertTrue(any("boot.md" in f.check for f in failed))


class TestCheckIntegrity(unittest.TestCase):
    def setUp(self) -> None:
        self.layout, self.tmp = make_layout()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def test_empty_files_map_fails(self) -> None:
        findings = check_integrity(self.layout)
        # no tracked files → one fail
        failed = [f for f in findings if not f.passed]
        self.assertTrue(any("tracked files" in f.check for f in failed))

    def test_matching_hash_passes(self) -> None:
        import hashlib
        content = b"# Boot Protocol\n"
        self.layout.boot_md.write_bytes(content)
        digest = "sha256:" + hashlib.sha256(content).hexdigest()
        doc = json.loads(self.layout.integrity_doc.read_text(encoding="utf-8"))
        doc["files"]["boot.md"] = digest
        atomic_write(self.layout.integrity_doc, doc)
        findings = check_integrity(self.layout)
        passed = [f for f in findings if f.passed and "boot.md" in f.check]
        self.assertTrue(len(passed) > 0)

    def test_mismatched_hash_fails(self) -> None:
        doc = json.loads(self.layout.integrity_doc.read_text(encoding="utf-8"))
        doc["files"]["boot.md"] = "a" * 64
        atomic_write(self.layout.integrity_doc, doc)
        findings = check_integrity(self.layout)
        failed = [f for f in findings if not f.passed and "boot.md" in f.check]
        self.assertTrue(len(failed) > 0)


class TestCheckChain(unittest.TestCase):
    def setUp(self) -> None:
        self.layout, self.tmp = make_layout()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def test_empty_chain_fails(self) -> None:
        findings = check_chain(self.layout)
        failed = [f for f in findings if not f.passed]
        self.assertTrue(any("empty" in f.check for f in failed))

    def test_valid_single_entry_passes(self) -> None:
        import hashlib
        entry = json.dumps({"seq": 0, "type": "genesis", "prev_hash": ""})
        self.layout.integrity_chain.write_text(entry + "\n", encoding="utf-8")
        findings = check_chain(self.layout)
        failed = [f for f in findings if not f.passed]
        self.assertEqual(failed, [], msg=str(failed))

    def test_broken_prev_hash_fails(self) -> None:
        import hashlib
        entry0 = json.dumps({"seq": 0, "type": "genesis", "prev_hash": ""})
        entry1 = json.dumps({"seq": 1, "type": "ENDURE_COMMIT",
                             "prev_hash": "wrong" * 10,
                             "evolution_auth_digest": "a" * 64})
        self.layout.integrity_chain.write_text(
            entry0 + "\n" + entry1 + "\n", encoding="utf-8"
        )
        findings = check_chain(self.layout)
        failed = [f for f in findings if not f.passed and "prev_hash" in f.check]
        self.assertTrue(len(failed) > 0)


class TestCheckSkills(unittest.TestCase):
    def setUp(self) -> None:
        self.layout, self.tmp = make_layout()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def test_missing_builtins_fail(self) -> None:
        findings = check_skills(self.layout)
        failed = [f for f in findings if not f.passed]
        # all 8 builtins not in index
        self.assertGreater(len(failed), 0)

    def test_installed_builtin_passes(self) -> None:
        # install file_reader
        skill_dir = self.layout.skills_lib_dir / "file_reader"
        skill_dir.mkdir(parents=True, exist_ok=True)
        manifest = {
            "name": "file_reader",
            "version": "1.0.0",
            "description": "Read files",
            "timeout_seconds": 10,
            "background": False,
            "irreversible": False,
            "class": "builtin",
            "permissions": [],
        }
        atomic_write(skill_dir / "manifest.json", manifest)
        (skill_dir / "run.py").write_text("", encoding="utf-8")
        idx = json.loads(self.layout.skills_index.read_text(encoding="utf-8"))
        idx["skills"].append({
            "name": "file_reader",
            "class": "builtin",
            "manifest": "skills/lib/file_reader/manifest.json",
        })
        atomic_write(self.layout.skills_index, idx)
        findings = check_skills(self.layout)
        passed = [f for f in findings if f.passed and "file_reader" in f.check]
        self.assertGreater(len(passed), 0)


class TestRunAll(unittest.TestCase):
    def setUp(self) -> None:
        self.layout, self.tmp = make_layout()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def test_run_all_returns_findings(self) -> None:
        findings = run_all(self.layout)
        self.assertGreater(len(findings), 0)
        # all are Finding instances
        from fcp_base.compliance import Finding
        for f in findings:
            self.assertIsInstance(f, Finding)


if __name__ == "__main__":
    unittest.main()
