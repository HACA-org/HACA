"""Tests for the Boot Sequence."""

import json
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

from fcp_base import boot
from fcp_base.store import Layout, append_jsonl, atomic_write, read_json
from tests.helpers import make_layout


def _patch_channel():
    return patch("fcp_base.boot.operator_channel_available", return_value=(True, True))


def _patch_fap(session_id: str = "fap-session-001"):
    return patch("fcp_base.boot.fap_run", return_value=session_id)


def _patch_sleep():
    return patch("fcp_base.boot.sleep_mod.run")


_GENESIS_TS = "2000-01-01T00:00:00Z"


def _write_valid_genesis(layout: Layout) -> None:
    """Write a minimal valid genesis entry to integrity_chain.jsonl."""
    entry = json.dumps({
        "seq": 1,
        "type": "genesis",
        "ts": _GENESIS_TS,
        "prev_hash": None,
        "imprint_hash": "0" * 64,
    })
    layout.integrity_chain.write_text(entry + "\n", encoding="utf-8")


def _make_valid_integrity_doc(layout: Layout) -> None:
    """Write an integrity doc with no tracked files (passes verify_structural_files)."""
    atomic_write(layout.integrity_doc, {
        "version": "1.0",
        "algorithm": "sha256",
        "genesis_omega": "0" * 64,
        "last_checkpoint": None,
        "files": {},
    })


class TestBootColdStart(unittest.TestCase):
    """Cold-start: imprint absent → FAP delegation."""

    def setUp(self) -> None:
        self.layout, self.tmp = make_layout()
        self.layout.imprint.unlink()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def test_cold_start_delegates_to_fap(self) -> None:
        with _patch_fap("fap-sid") as mock_fap:
            result = boot.run(self.layout)
        mock_fap.assert_called_once_with(self.layout)
        self.assertEqual(result.session_id, "fap-sid")
        self.assertTrue(result.is_first_boot)

    def test_cold_start_result_flags(self) -> None:
        with _patch_fap():
            result = boot.run(self.layout)
        self.assertTrue(result.is_first_boot)
        self.assertFalse(result.crash_recovered)


class TestBootPhase0(unittest.TestCase):
    """Phase 0 — Operator Bound Verification."""

    def setUp(self) -> None:
        self.layout, self.tmp = make_layout()
        _write_valid_genesis(self.layout)
        _make_valid_integrity_doc(self.layout)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def test_invalid_imprint_raises(self) -> None:
        atomic_write(self.layout.imprint, {"bad": "data"})
        with _patch_channel():
            with self.assertRaises(boot.BootError) as cm:
                boot.run(self.layout)
        self.assertIn("Phase 0", str(cm.exception))

    def test_no_notifications_dir_raises(self) -> None:
        with patch("fcp_base.boot.operator_channel_available", return_value=(False, True)):
            with self.assertRaises(boot.BootError) as cm:
                boot.run(self.layout)
        self.assertIn("Phase 0", str(cm.exception))

    def test_no_terminal_raises(self) -> None:
        with patch("fcp_base.boot.operator_channel_available", return_value=(True, False)):
            with self.assertRaises(boot.BootError) as cm:
                boot.run(self.layout)
        self.assertIn("Phase 0", str(cm.exception))


class TestBootPhase1(unittest.TestCase):
    """Phase 1 — Host Introspection."""

    def setUp(self) -> None:
        self.layout, self.tmp = make_layout()
        _write_valid_genesis(self.layout)
        _make_valid_integrity_doc(self.layout)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def test_opaque_topology_raises(self) -> None:
        baseline = read_json(self.layout.baseline)
        baseline["cpe"]["topology"] = "opaque"
        atomic_write(self.layout.baseline, baseline)
        with _patch_channel():
            with self.assertRaises(boot.BootError) as cm:
                boot.run(self.layout)
        self.assertIn("topology", str(cm.exception))

    def test_watchdog_exceeds_heartbeat_raises(self) -> None:
        baseline = read_json(self.layout.baseline)
        baseline["watchdog"]["sil_threshold_seconds"] = 999
        atomic_write(self.layout.baseline, baseline)
        with _patch_channel():
            with self.assertRaises(boot.BootError) as cm:
                boot.run(self.layout)
        self.assertIn("watchdog", str(cm.exception))


class TestBootPhase2CrashRecovery(unittest.TestCase):
    """Phase 2 — Crash Recovery (stale session token)."""

    def setUp(self) -> None:
        self.layout, self.tmp = make_layout()
        _write_valid_genesis(self.layout)
        _make_valid_integrity_doc(self.layout)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def test_stale_token_triggers_crash_recovery(self) -> None:
        atomic_write(self.layout.session_token, {
            "session_id": "stale-sid",
            "issued_at": "2000-01-01T00:00:00Z",
            "revoked_at": None,
        })
        with _patch_channel():
            # sleep is imported locally inside _crash_recovery; patch the module
            with patch("fcp_base.sleep.run_sleep_cycle"):
                with patch("fcp_base.boot._resolve_action_ledger"):
                    result = boot.run(self.layout)
        self.assertTrue(result.crash_recovered)

    def test_no_stale_token_no_crash_recovery(self) -> None:
        with _patch_channel():
            result = boot.run(self.layout)
        self.assertFalse(result.crash_recovered)


class TestBootPhase3Integrity(unittest.TestCase):
    """Phase 3 — Integrity Verification."""

    def setUp(self) -> None:
        self.layout, self.tmp = make_layout()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def test_broken_chain_raises(self) -> None:
        e0 = json.dumps({
            "seq": 1, "type": "genesis", "ts": _GENESIS_TS,
            "prev_hash": None, "imprint_hash": "0" * 64,
        })
        e1 = json.dumps({
            "seq": 2, "type": "ENDURE_COMMIT", "ts": _GENESIS_TS,
            "prev_hash": "wrong" * 10,
            "evolution_auth_digest": "a" * 64,
        })
        self.layout.integrity_chain.write_text(e0 + "\n" + e1 + "\n", encoding="utf-8")
        _make_valid_integrity_doc(self.layout)
        with _patch_channel():
            with self.assertRaises(boot.BootError) as cm:
                boot.run(self.layout)
        self.assertIn("Phase 3", str(cm.exception))

    def test_hash_mismatch_raises(self) -> None:
        _write_valid_genesis(self.layout)
        # Integrity doc tracks boot.md with a wrong hash
        atomic_write(self.layout.integrity_doc, {
            "version": "1.0",
            "algorithm": "sha256",
            "genesis_omega": "0" * 64,
            "last_checkpoint": None,
            "files": {"boot.md": "sha256:" + "a" * 64},
        })
        with _patch_channel():
            with self.assertRaises(boot.BootError) as cm:
                boot.run(self.layout)
        self.assertIn("Phase 3", str(cm.exception))


class TestBootPhase6Critical(unittest.TestCase):
    """Phase 6 — Critical Condition Check."""

    def setUp(self) -> None:
        self.layout, self.tmp = make_layout()
        _write_valid_genesis(self.layout)
        _make_valid_integrity_doc(self.layout)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def test_unresolved_critical_raises(self) -> None:
        entry = {
            "actor": "sil", "gseq": 0, "tx": "t", "seq": 1, "eof": True,
            "type": "DRIFT_FAULT", "ts": "2000-01-01T00:00:00Z",
            "data": "{}", "crc": "00000000",
        }
        append_jsonl(self.layout.integrity_log, entry)
        with _patch_channel():
            with self.assertRaises(boot.BootError) as cm:
                boot.run(self.layout)
        self.assertIn("Phase 6", str(cm.exception))

    def test_cleared_critical_passes(self) -> None:
        fault = {
            "actor": "sil", "gseq": 0, "tx": "t1", "seq": 1, "eof": True,
            "type": "DRIFT_FAULT", "ts": "2000-01-01T00:00:00Z",
            "data": "{}", "crc": "00000000",
        }
        clear = {
            "actor": "sil", "gseq": 1, "tx": "t2", "seq": 1, "eof": True,
            "type": "CRITICAL_CLEARED", "ts": "2000-01-01T00:00:01Z",
            "data": json.dumps({"clears_seq": 1}), "crc": "00000000",
        }
        append_jsonl(self.layout.integrity_log, fault)
        append_jsonl(self.layout.integrity_log, clear)
        with _patch_channel():
            result = boot.run(self.layout)
        self.assertIsInstance(result, boot.BootResult)

    def test_pending_proposals_returned(self) -> None:
        proposal = {
            "actor": "sil", "gseq": 0, "tx": "tp", "seq": 1, "eof": True,
            "type": "PROPOSAL_PENDING", "ts": "2000-01-01T00:00:00Z",
            "data": json.dumps({"slug": "react-rules", "promotion": True}),
            "crc": "00000000",
        }
        append_jsonl(self.layout.integrity_log, proposal)
        with _patch_channel():
            result = boot.run(self.layout)
        self.assertGreater(len(result.pending_proposals), 0)
        self.assertEqual(result.pending_proposals[0]["slug"], "react-rules")


class TestBootPhase7TokenIssuance(unittest.TestCase):
    """Phase 7 — Session Token Issuance."""

    def setUp(self) -> None:
        self.layout, self.tmp = make_layout()
        _write_valid_genesis(self.layout)
        _make_valid_integrity_doc(self.layout)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def test_session_token_written(self) -> None:
        with _patch_channel():
            boot.run(self.layout)
        self.assertTrue(self.layout.session_token.exists())

    def test_session_id_returned(self) -> None:
        with _patch_channel():
            result = boot.run(self.layout)
        self.assertIsInstance(result.session_id, str)
        self.assertGreater(len(result.session_id), 0)

    def test_session_id_matches_token(self) -> None:
        with _patch_channel():
            result = boot.run(self.layout)
        token = read_json(self.layout.session_token)
        self.assertEqual(result.session_id, token["session_id"])


if __name__ == "__main__":
    unittest.main()
