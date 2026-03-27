"""Tests for fcp_base.cmi.dispatch and compliance.check_cmi."""

import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fcp_base.store import Layout, atomic_write, read_json
from fcp_base.cmi.identity import generate_cmi_credential
from fcp_base.cmi.dispatch import dispatch_send, dispatch_req
from fcp_base.compliance import check_cmi, Finding
from tests.helpers import make_layout


CHAN_ID = "chan_test0001"

CHANNEL_ACTIVE = {
    "id": CHAN_ID,
    "task": "test",
    "role": "host",
    "participants": [],
    "status": "active",
}


def _make_layout_with_cmi(channel_status: str = "active", role: str = "host") -> tuple[Layout, Path]:
    layout, tmp = make_layout()

    genesis = json.dumps({
        "seq": 1, "type": "GENESIS", "ts": "2026-01-01T00:00:00Z",
        "imprint_hash": "testhash123",
    })
    layout.integrity_chain.write_text(genesis + "\n", encoding="utf-8")
    generate_cmi_credential(layout)

    baseline = read_json(layout.baseline)
    cred = read_json(layout.cmi_credential)
    baseline["cmi"] = {
        "enabled": True,
        "node_identity": cred["node_identity"],
        "endpoint": "http://localhost:17700",
        "host": "http://localhost:17700",
        "contacts": [],
        "channels": [dict(CHANNEL_ACTIVE, status=channel_status, role=role)],
    }
    atomic_write(layout.baseline, baseline)
    return layout, tmp


# ---------------------------------------------------------------------------
# dispatch_send
# ---------------------------------------------------------------------------

class TestDispatchSend(unittest.TestCase):

    def setUp(self):
        self.layout, self.tmp = _make_layout_with_cmi()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_missing_chan_id(self):
        result = dispatch_send(self.layout, {"type": "general", "content": "hello"})
        self.assertIn("error", result)
        self.assertIn("chan_id", result["error"])

    def test_invalid_type(self):
        result = dispatch_send(self.layout, {"chan_id": CHAN_ID, "type": "bad", "content": "hi"})
        self.assertIn("error", result)
        self.assertIn("type", result["error"])

    def test_missing_content(self):
        result = dispatch_send(self.layout, {"chan_id": CHAN_ID, "type": "general", "content": ""})
        self.assertIn("error", result)
        self.assertIn("content", result["error"])

    def test_peer_requires_to(self):
        result = dispatch_send(self.layout, {"chan_id": CHAN_ID, "type": "peer", "content": "hi"})
        self.assertIn("error", result)
        self.assertIn("to", result["error"])

    def test_channel_not_found(self):
        result = dispatch_send(self.layout, {"chan_id": "chan_unknown", "type": "general", "content": "hi"})
        self.assertIn("error", result)
        self.assertIn("not found", result["error"])

    def test_channel_not_active(self):
        layout, tmp = _make_layout_with_cmi(channel_status="created")
        try:
            result = dispatch_send(layout, {"chan_id": CHAN_ID, "type": "general", "content": "hi"})
            self.assertIn("error", result)
            self.assertIn("not active", result["error"])
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_send_general_success(self):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"ok": True}).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = dispatch_send(self.layout, {
                "chan_id": CHAN_ID, "type": "general", "content": "hello world",
            })
        self.assertEqual(result["status"], "sent")
        self.assertEqual(result["chan_id"], CHAN_ID)
        self.assertEqual(result["type"], "general")

    def test_send_bb_uses_contribute_path(self):
        called_url = []

        def fake_urlopen(req, timeout=None):
            called_url.append(req.full_url)
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps({"ok": True}).encode()
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            return mock_resp

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            dispatch_send(self.layout, {"chan_id": CHAN_ID, "type": "bb", "content": "contribution"})

        self.assertTrue(called_url[0].endswith("/contribute"))

    def test_send_general_uses_message_path(self):
        called_url = []

        def fake_urlopen(req, timeout=None):
            called_url.append(req.full_url)
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps({"ok": True}).encode()
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            return mock_resp

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            dispatch_send(self.layout, {"chan_id": CHAN_ID, "type": "general", "content": "hi"})

        self.assertTrue(called_url[0].endswith("/message"))

    def test_network_error(self):
        import urllib.error
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("refused")):
            result = dispatch_send(self.layout, {"chan_id": CHAN_ID, "type": "general", "content": "hi"})
        self.assertIn("error", result)
        self.assertIn("unreachable", result["error"])

    def test_no_baseline(self):
        self.layout.baseline.unlink()
        result = dispatch_send(self.layout, {"chan_id": CHAN_ID, "type": "general", "content": "hi"})
        self.assertIn("error", result)


# ---------------------------------------------------------------------------
# dispatch_req
# ---------------------------------------------------------------------------

class TestDispatchReq(unittest.TestCase):

    def setUp(self):
        self.layout, self.tmp = _make_layout_with_cmi()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_invalid_op(self):
        result = dispatch_req(self.layout, {"op": "bad", "chan_id": CHAN_ID})
        self.assertIn("error", result)
        self.assertIn("op", result["error"])

    def test_missing_chan_id(self):
        result = dispatch_req(self.layout, {"op": "bb"})
        self.assertIn("error", result)
        self.assertIn("chan_id", result["error"])

    def test_channel_not_found(self):
        result = dispatch_req(self.layout, {"op": "bb", "chan_id": "chan_unknown"})
        self.assertIn("error", result)
        self.assertIn("not found", result["error"])

    def test_channel_closed_rejected(self):
        layout, tmp = _make_layout_with_cmi(channel_status="closed")
        try:
            result = dispatch_req(layout, {"op": "bb", "chan_id": CHAN_ID})
            self.assertIn("error", result)
            self.assertIn("closed", result["error"])
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_req_bb_success(self):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"entries": []}).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = dispatch_req(self.layout, {"op": "bb", "chan_id": CHAN_ID})
        self.assertEqual(result["op"], "bb")
        self.assertEqual(result["chan_id"], CHAN_ID)
        self.assertIn("entries", result)

    def test_req_status_success(self):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"status": "active", "participants": []}).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = dispatch_req(self.layout, {"op": "status", "chan_id": CHAN_ID})
        self.assertEqual(result["op"], "status")
        self.assertEqual(result["chan_id"], CHAN_ID)

    def test_req_bb_uses_bb_path(self):
        called_url = []

        def fake_urlopen(req, timeout=None):
            called_url.append(req.full_url)
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps({"entries": []}).encode()
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            return mock_resp

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            dispatch_req(self.layout, {"op": "bb", "chan_id": CHAN_ID})

        self.assertTrue(called_url[0].endswith("/bb"))

    def test_network_error(self):
        import urllib.error
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("refused")):
            result = dispatch_req(self.layout, {"op": "bb", "chan_id": CHAN_ID})
        self.assertIn("error", result)
        self.assertIn("unreachable", result["error"])


# ---------------------------------------------------------------------------
# compliance.check_cmi
# ---------------------------------------------------------------------------

class TestCheckCmi(unittest.TestCase):

    def setUp(self):
        self.layout, self.tmp = make_layout()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _set_cmi(self, enabled: bool, host: str = ""):
        baseline = read_json(self.layout.baseline)
        baseline["cmi"] = {"enabled": enabled, "host": host}
        atomic_write(self.layout.baseline, baseline)

    def test_cmi_not_enabled_skipped(self):
        self._set_cmi(enabled=False)
        findings = check_cmi(self.layout)
        self.assertTrue(all(f.passed for f in findings))
        self.assertTrue(any("not enabled" in f.check for f in findings))

    def test_cmi_enabled_with_host_passes(self):
        self._set_cmi(enabled=True, host="http://localhost:17700")
        findings = check_cmi(self.layout)
        failures = [f for f in findings if not f.passed]
        self.assertEqual(failures, [])

    def test_cmi_enabled_without_host_fails(self):
        self._set_cmi(enabled=True, host="")
        findings = check_cmi(self.layout)
        failures = [f for f in findings if not f.passed]
        self.assertEqual(len(failures), 1)
        self.assertIn("host", failures[0].detail)

    def test_cmi_key_absent_treated_as_not_enabled(self):
        # baseline with no cmi key at all
        baseline = read_json(self.layout.baseline)
        baseline.pop("cmi", None)
        atomic_write(self.layout.baseline, baseline)
        findings = check_cmi(self.layout)
        self.assertTrue(all(f.passed for f in findings))

    def test_baseline_missing_returns_fail(self):
        self.layout.baseline.unlink()
        findings = check_cmi(self.layout)
        self.assertTrue(any(not f.passed for f in findings))
