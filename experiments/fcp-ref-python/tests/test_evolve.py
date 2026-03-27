"""Tests for HACA-Evolve profile behavior.

Covers:
  - Drift tolerance (semantic drift warning instead of fault)
  - Identity drift → Degraded → escalate to Critical
  - Scope-gated proposals (in-scope executed, out-of-scope notified)
  - Public CMI enrollment
"""

from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path

from helpers import make_evolve_layout, make_layout, _atomic_write
from fcp_base.sleep import _stage0_drift, _stage3_endure, _op_in_scope
from fcp_base.vital import _check_identity_drift
from fcp_base.acp import make as acp_encode
from fcp_base.store import append_jsonl


# ---------------------------------------------------------------------------
# _op_in_scope
# ---------------------------------------------------------------------------

class TestOpInScope(unittest.TestCase):

    def test_file_ops_require_autonomous_evolution(self):
        scope = {"autonomous_evolution": True, "autonomous_skills": False}
        self.assertTrue(_op_in_scope("json_merge", scope))
        self.assertTrue(_op_in_scope("file_write", scope))
        self.assertTrue(_op_in_scope("file_delete", scope))

    def test_file_ops_blocked_without_autonomous_evolution(self):
        scope = {"autonomous_evolution": False}
        self.assertFalse(_op_in_scope("json_merge", scope))
        self.assertFalse(_op_in_scope("file_write", scope))
        self.assertFalse(_op_in_scope("file_delete", scope))

    def test_skill_install_requires_autonomous_skills(self):
        self.assertTrue(_op_in_scope("skill_install", {"autonomous_skills": True}))
        self.assertFalse(_op_in_scope("skill_install", {"autonomous_skills": False}))

    def test_cmi_peer_add_requires_cmi_access(self):
        self.assertTrue(_op_in_scope("cmi_peer_add", {"cmi_access": "private"}))
        self.assertTrue(_op_in_scope("cmi_peer_add", {"cmi_access": "both"}))
        self.assertFalse(_op_in_scope("cmi_peer_add", {"cmi_access": "none"}))

    def test_cron_add_always_out_of_scope(self):
        scope = {"autonomous_evolution": True, "autonomous_skills": True, "cmi_access": "both"}
        self.assertFalse(_op_in_scope("cron_add", scope))


# ---------------------------------------------------------------------------
# Semantic drift — Evolve tolerance
# ---------------------------------------------------------------------------

class TestEvolveDriftTolerance(unittest.TestCase):

    def setUp(self):
        self.layout, self.tmp = make_evolve_layout()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_drift_generates_warning_not_fault(self):
        """Evolve with threshold > 0: probe failure → warning, not DRIFT_FAULT."""
        # Create a probe that will fail
        probe_target = self.tmp / "boot.md"
        probes = [{"target": "boot.md", "reference": "sha256:" + "0" * 64, "type": "hash"}]
        from fcp_base.store import append_jsonl
        for p in probes:
            append_jsonl(self.layout.drift_probes, p)

        fault = _stage0_drift(self.layout)
        self.assertFalse(fault)  # No fault raised

        # Warning notification should exist
        notifs = list((self.tmp / "state" / "operator_notifications").iterdir())
        warning_notifs = [n for n in notifs if "warning" in n.name or n.read_text().find("SEMANTIC_DRIFT_WARNING") >= 0]
        self.assertTrue(len(warning_notifs) > 0)

    def test_drift_fault_on_zero_threshold(self):
        """Evolve with threshold == 0: same as Core — DRIFT_FAULT raised."""
        layout, tmp = make_evolve_layout(scope={
            "autonomous_evolution": True, "autonomous_skills": False,
            "cmi_access": "none", "operator_memory": False, "renewal_days": 0,
        })
        try:
            # Override threshold to 0
            baseline_path = tmp / "state" / "baseline.json"
            with open(baseline_path) as f:
                b = json.load(f)
            b["drift"]["threshold"] = 0.0
            _atomic_write(baseline_path, b)

            probes = [{"target": "boot.md", "reference": "sha256:" + "0" * 64, "type": "hash"}]
            from fcp_base.store import append_jsonl
            for p in probes:
                append_jsonl(layout.drift_probes, p)

            fault = _stage0_drift(layout)
            self.assertTrue(fault)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Identity drift — Degraded → Critical
# ---------------------------------------------------------------------------

class TestEvolveIdentityDrift(unittest.TestCase):

    def setUp(self):
        self.layout, self.tmp = make_evolve_layout()
        # Track a persona file in integrity doc with wrong hash (simulates drift)
        persona_file = self.tmp / "persona" / "00-base.md"
        persona_file.write_text("You are a helpful assistant.\n", encoding="utf-8")
        doc_path = self.tmp / "state" / "integrity.json"
        with open(doc_path) as f:
            doc = json.load(f)
        doc["files"]["persona/00-base.md"] = "sha256:" + "0" * 64  # wrong hash
        _atomic_write(doc_path, doc)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_first_drift_is_degraded(self):
        result = _check_identity_drift(self.layout)
        self.assertEqual(result, ["identity_degraded"])
        # Sentinel should exist
        sentinel = self.tmp / "state" / "sentinels" / "identity_degraded"
        self.assertTrue(sentinel.exists())

    def test_second_drift_escalates_to_critical(self):
        # First call → Degraded + sentinel
        _check_identity_drift(self.layout)
        # Second call → Critical
        result = _check_identity_drift(self.layout)
        self.assertEqual(result, ["identity_drift"])
        # Sentinel should be cleared
        sentinel = self.tmp / "state" / "sentinels" / "identity_degraded"
        self.assertFalse(sentinel.exists())

    def test_core_drift_is_always_critical(self):
        layout, tmp = make_layout()
        try:
            persona_file = tmp / "persona" / "00-base.md"
            persona_file.write_text("You are a helpful assistant.\n", encoding="utf-8")
            doc_path = tmp / "state" / "integrity.json"
            with open(doc_path) as f:
                doc = json.load(f)
            doc["files"]["persona/00-base.md"] = "sha256:" + "0" * 64
            _atomic_write(doc_path, doc)

            result = _check_identity_drift(layout)
            self.assertEqual(result, ["identity_drift"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Scope-gated proposals
# ---------------------------------------------------------------------------

class TestEvolveProposalScope(unittest.TestCase):

    def _write_evolution_auth(self, layout, changes: list) -> None:
        """Write a minimal EVOLUTION_AUTH entry to integrity.log via ACP envelope."""
        data = {
            "type": "EVOLUTION_AUTH",
            "auth_digest": "test-digest",
            "content": {"changes": changes},
            "slugs": [],
        }
        append_jsonl(layout.integrity_log, acp_encode(
            env_type="MSG", source="sil", data=data
        ))

    def test_in_scope_proposal_executes(self):
        layout, tmp = make_evolve_layout()
        try:
            target = tmp / "state" / "extra.json"
            self._write_evolution_auth(layout, [{
                "op": "file_write",
                "target": "state/extra.json",
                "content": '{"ok": true}',
            }])
            _stage3_endure(layout)
            self.assertTrue(target.exists())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_out_of_scope_proposal_skipped_with_notification(self):
        layout, tmp = make_evolve_layout(scope={
            "autonomous_evolution": False,  # file_write out of scope
            "autonomous_skills": False,
            "cmi_access": "none",
            "operator_memory": False,
            "renewal_days": 30,
        })
        try:
            target = tmp / "state" / "extra.json"
            self._write_evolution_auth(layout, [{
                "op": "file_write",
                "target": "state/extra.json",
                "content": '{"ok": true}',
            }])
            _stage3_endure(layout)
            self.assertFalse(target.exists())

            # Out-of-scope notification should exist
            notifs = list((tmp / "state" / "operator_notifications").iterdir())
            oos = [n for n in notifs if "EVOLUTION_OUT_OF_SCOPE" in n.read_text()]
            self.assertTrue(len(oos) > 0)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_cron_add_always_held_in_evolve(self):
        """cron_add is never in-scope — always requires explicit approval."""
        layout, tmp = make_evolve_layout()
        try:
            self._write_evolution_auth(layout, [{
                "op": "cron_add",
                "description": "Daily report",
                "executor": "worker",
                "task": "Summarise the day",
                "schedule": "0 9 * * *",
            }])
            _stage3_endure(layout)
            # agenda.json should NOT be created (proposal skipped as out-of-scope)
            self.assertFalse(layout.agenda.exists())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
