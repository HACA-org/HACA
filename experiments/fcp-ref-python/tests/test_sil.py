"""Tests for the sil/ package (utils, integrity, beacon, chain, dispatch)."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from fcp_base.store import Layout


def _make_layout() -> tuple[Layout, Path]:
    tmp = Path(tempfile.mkdtemp())
    # minimal directory structure expected by Layout
    (tmp / "state" / "operator_notifications").mkdir(parents=True)
    (tmp / "state" / "sentinels").mkdir(parents=True)
    (tmp / "skills" / "lib").mkdir(parents=True)
    (tmp / "skills").mkdir(parents=True, exist_ok=True)
    (tmp / "persona").mkdir(parents=True)
    # minimal required files
    (tmp / "boot.md").write_text("# boot", encoding="utf-8")
    (tmp / "state" / "baseline.json").write_text("{}", encoding="utf-8")
    (tmp / "skills" / "index.json").write_text('{"version":"1.0","skills":[]}', encoding="utf-8")
    return Layout(tmp), tmp


# ---------------------------------------------------------------------------
# utils
# ---------------------------------------------------------------------------

class TestSilUtils(unittest.TestCase):

    def test_utcnow_format(self):
        from fcp_base.sil import utcnow
        ts = utcnow()
        self.assertRegex(ts, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

    def test_sha256_str(self):
        from fcp_base.sil import sha256_str
        result = sha256_str("hello")
        self.assertTrue(result.startswith("sha256:"))
        self.assertEqual(len(result), 7 + 64)

    def test_sha256_str_deterministic(self):
        from fcp_base.sil import sha256_str
        self.assertEqual(sha256_str("abc"), sha256_str("abc"))
        self.assertNotEqual(sha256_str("abc"), sha256_str("xyz"))

    def test_sha256_bytes(self):
        from fcp_base.sil import sha256_bytes
        result = sha256_bytes(b"data")
        self.assertTrue(result.startswith("sha256:"))

    def test_sha256_file(self):
        from fcp_base.sil import sha256_file
        tmp = Path(tempfile.mktemp(suffix=".txt"))
        try:
            tmp.write_bytes(b"content")
            result = sha256_file(tmp)
            self.assertTrue(result.startswith("sha256:"))
        finally:
            tmp.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# integrity
# ---------------------------------------------------------------------------

class TestSilIntegrity(unittest.TestCase):

    def setUp(self):
        self.layout, self.tmp = _make_layout()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_tracked_files_includes_boot_md(self):
        from fcp_base.sil import tracked_files
        paths = tracked_files(self.layout)
        self.assertIn(self.layout.boot_md, paths)

    def test_tracked_files_includes_baseline(self):
        from fcp_base.sil import tracked_files
        paths = tracked_files(self.layout)
        self.assertIn(self.layout.baseline, paths)

    def test_compute_integrity_files_returns_hashes(self):
        from fcp_base.sil import compute_integrity_files
        files = compute_integrity_files(self.layout)
        self.assertIsInstance(files, dict)
        for v in files.values():
            self.assertTrue(v.startswith("sha256:"))

    def test_write_and_verify_structural_files_clean(self):
        from fcp_base.sil import compute_integrity_files, write_integrity_doc
        from fcp_base.formats import IntegrityDocument
        files = compute_integrity_files(self.layout)
        write_integrity_doc(self.layout, files)
        self.assertTrue(self.layout.integrity_doc.exists())
        doc = IntegrityDocument.from_dict(
            json.loads(self.layout.integrity_doc.read_text())
        )
        from fcp_base.sil import verify_structural_files
        mismatches = verify_structural_files(self.layout, doc)
        self.assertEqual(mismatches, [])

    def test_verify_structural_files_detects_missing(self):
        from fcp_base.sil import compute_integrity_files, write_integrity_doc, verify_structural_files
        from fcp_base.formats import IntegrityDocument
        files = compute_integrity_files(self.layout)
        # inject a fake entry for a non-existent file
        files["state/nonexistent.json"] = "sha256:abc123"
        write_integrity_doc(self.layout, files)
        doc = IntegrityDocument.from_dict(
            json.loads(self.layout.integrity_doc.read_text())
        )
        mismatches = verify_structural_files(self.layout, doc)
        self.assertTrue(any("nonexistent" in m for m in mismatches))

    def test_verify_structural_files_detects_hash_mismatch(self):
        from fcp_base.sil import compute_integrity_files, write_integrity_doc, verify_structural_files
        from fcp_base.formats import IntegrityDocument
        files = compute_integrity_files(self.layout)
        # corrupt the baseline hash
        rel = str(self.layout.baseline.relative_to(self.layout.root))
        files[rel] = "sha256:" + "0" * 64
        write_integrity_doc(self.layout, files)
        doc = IntegrityDocument.from_dict(
            json.loads(self.layout.integrity_doc.read_text())
        )
        mismatches = verify_structural_files(self.layout, doc)
        self.assertTrue(any("mismatch" in m for m in mismatches))


# ---------------------------------------------------------------------------
# beacon
# ---------------------------------------------------------------------------

class TestSilBeacon(unittest.TestCase):

    def setUp(self):
        self.layout, self.tmp = _make_layout()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_beacon_not_active_initially(self):
        from fcp_base.sil import beacon_is_active
        self.assertFalse(beacon_is_active(self.layout))

    def test_activate_beacon_creates_file(self):
        from fcp_base.sil import activate_beacon, beacon_is_active
        activate_beacon(self.layout, cause="test", consecutive_failures=2)
        self.assertTrue(beacon_is_active(self.layout))
        data = json.loads(self.layout.distress_beacon.read_text())
        self.assertEqual(data["cause"], "test")
        self.assertEqual(data["consecutive_failures"], 2)

    def test_clear_beacon_removes_file(self):
        from fcp_base.sil import activate_beacon, clear_beacon, beacon_is_active
        activate_beacon(self.layout, cause="test", consecutive_failures=1)
        clear_beacon(self.layout)
        self.assertFalse(beacon_is_active(self.layout))

    def test_clear_beacon_noop_when_not_active(self):
        from fcp_base.sil import clear_beacon
        clear_beacon(self.layout)  # must not raise

    def test_session_token_not_present_initially(self):
        from fcp_base.sil import session_token_present
        self.assertFalse(session_token_present(self.layout))

    def test_issue_session_token_returns_uuid(self):
        from fcp_base.sil import issue_session_token, session_token_present
        sid = issue_session_token(self.layout)
        self.assertIsInstance(sid, str)
        self.assertEqual(len(sid), 36)  # UUID4 format
        self.assertTrue(session_token_present(self.layout))

    def test_revoke_session_token_stamps_revoked_at(self):
        from fcp_base.sil import issue_session_token, revoke_session_token, read_session_token
        issue_session_token(self.layout)
        revoke_session_token(self.layout)
        token = read_session_token(self.layout)
        self.assertIsNotNone(token)
        self.assertIsNotNone(token.revoked_at)

    def test_read_session_token_returns_none_when_absent(self):
        from fcp_base.sil import read_session_token
        self.assertIsNone(read_session_token(self.layout))


# ---------------------------------------------------------------------------
# chain
# ---------------------------------------------------------------------------

class TestSilChain(unittest.TestCase):

    def setUp(self):
        self.layout, self.tmp = _make_layout()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_log_heartbeat_appends_to_integrity_log(self):
        from fcp_base.sil import log_heartbeat
        log_heartbeat(self.layout, "test-session-id")
        self.assertTrue(self.layout.integrity_log.exists())
        lines = self.layout.integrity_log.read_text().splitlines()
        self.assertEqual(len(lines), 1)
        rec = json.loads(lines[0])
        self.assertEqual(rec["type"], "HEARTBEAT")

    def test_log_sleep_complete_appends_record(self):
        from fcp_base.sil import log_sleep_complete
        log_sleep_complete(self.layout, "sess-42")
        lines = self.layout.integrity_log.read_text().splitlines()
        rec = json.loads(lines[0])
        self.assertEqual(rec["type"], "SLEEP_COMPLETE")

    def test_log_critical_appends_record(self):
        from fcp_base.sil import log_critical
        log_critical(self.layout, "DRIFT_FAULT", {"detail": "drift detected"})
        lines = self.layout.integrity_log.read_text().splitlines()
        rec = json.loads(lines[0])
        self.assertEqual(rec["type"], "DRIFT_FAULT")

    def test_last_chain_seq_empty(self):
        from fcp_base.sil import last_chain_seq
        self.assertEqual(last_chain_seq(self.layout), 0)

    def test_write_and_read_chain_entry(self):
        from fcp_base.sil import write_chain_entry, last_chain_seq
        from fcp_base.formats import ChainEntry, ChainEntryType
        from fcp_base.sil import sha256_str
        entry = ChainEntry(
            seq=1,
            type=ChainEntryType.GENESIS,
            ts="2026-01-01T00:00:00Z",
            prev_hash=None,
            imprint_hash=sha256_str("boot"),
            evolution_auth_digest=None,
        )
        write_chain_entry(self.layout, entry)
        self.assertEqual(last_chain_seq(self.layout), 1)

    def test_write_evolution_auth_appends_to_log(self):
        from fcp_base.sil import write_evolution_auth
        write_evolution_auth(self.layout, '{"desc":"test"}', "sha256:" + "a" * 64)
        lines = self.layout.integrity_log.read_text().splitlines()
        self.assertEqual(len(lines), 1)
        rec = json.loads(lines[0])
        # EVOLUTION_AUTH is wrapped in an ACP MSG envelope
        data = json.loads(rec["data"])
        self.assertEqual(data["type"], "EVOLUTION_AUTH")


# ---------------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------------

class TestSilDispatch(unittest.TestCase):

    def setUp(self):
        self.layout, self.tmp = _make_layout()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_write_notification_creates_file(self):
        from fcp_base.sil import write_notification
        path = write_notification(self.layout, "test_event", {"msg": "hello"})
        self.assertTrue(path.exists())
        data = json.loads(path.read_text())
        self.assertEqual(data["msg"], "hello")

    def test_write_notification_filename_contains_severity(self):
        from fcp_base.sil import write_notification
        path = write_notification(self.layout, "shell_run_blocked", {"cmd": "rm -rf"})
        self.assertIn("shell_run_blocked", path.name)

    def test_stage_evolution_proposal_creates_file(self):
        from fcp_base.sil import stage_evolution_proposal
        path = stage_evolution_proposal(self.layout, '{"description":"add skill"}')
        self.assertTrue(path.exists())
        data = json.loads(path.read_text())
        inner = json.loads(data["data"])
        self.assertEqual(inner["type"], "PROPOSAL_PENDING")

    def test_operator_channel_available_returns_tuple(self):
        from fcp_base.sil import operator_channel_available
        result = operator_channel_available(self.layout)
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)
        notif_ok, terminal_ok = result
        self.assertIsInstance(notif_ok, bool)
        self.assertIsInstance(terminal_ok, bool)


if __name__ == "__main__":
    unittest.main()
