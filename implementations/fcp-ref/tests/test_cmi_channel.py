"""Tests for fcp_core.cmi.channel_process — ChannelProcess internals."""

import json
import shutil
import unittest
from pathlib import Path

from fcp_core.store import Layout, atomic_write, read_json, read_jsonl
from fcp_core.cmi.identity import generate_cmi_credential
from fcp_core.cmi.channel_process import ChannelProcess
from fcp_core.acp import decode as acp_decode
from tests.helpers import make_layout


def _read_inbox_data(path: Path) -> dict:
    """Read an ACP .msg file and return the decoded data dict."""
    env = acp_decode(path.read_text(encoding="utf-8"))
    return json.loads(env.data)


CHAN_ID = "chan_test0001"

CHANNEL_CFG = {
    "id": CHAN_ID,
    "task": "Test collaboration task",
    "role": "host",
    "participants": [],
    "status": "created",
}


def _make_layout_with_cmi(role: str = "host") -> tuple[Layout, Path]:
    layout, tmp = make_layout()

    # Add genesis entry for credential derivation
    import json as _j
    genesis = _j.dumps({
        "seq": 1, "type": "GENESIS", "ts": "2026-01-01T00:00:00Z",
        "imprint_hash": "testhash123",
    })
    layout.integrity_chain.write_text(genesis + "\n", encoding="utf-8")

    # Generate credential
    generate_cmi_credential(layout)

    # Add CMI config to baseline
    baseline = read_json(layout.baseline)
    cred = read_json(layout.cmi_credential)
    baseline["cmi"] = {
        "enabled": True,
        "node_identity": cred["node_identity"],
        "endpoint": "http://localhost:17700",
        "trusted_peers": [],
        "channels": [dict(CHANNEL_CFG, role=role)],
    }
    atomic_write(layout.baseline, baseline)

    return layout, tmp


def _make_process(layout: Layout, role: str = "host") -> ChannelProcess:
    return ChannelProcess(layout, CHAN_ID, role)


class TestChannelProcessInit(unittest.TestCase):

    def setUp(self):
        self.layout, self.tmp = _make_layout_with_cmi()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_creates_channel_dir(self):
        _make_process(self.layout)
        self.assertTrue(self.layout.cmi_channel_dir(CHAN_ID).exists())

    def test_loads_credential(self):
        proc = _make_process(self.layout)
        self.assertIsNotNone(proc._credential)
        self.assertIn("node_identity", proc._credential)

    def test_finds_channel_cfg(self):
        proc = _make_process(self.layout)
        self.assertEqual(proc._channel_cfg.get("id"), CHAN_ID)
        self.assertEqual(proc._channel_cfg.get("task"), "Test collaboration task")

    def test_missing_credential_is_none(self):
        layout, tmp = make_layout()
        try:
            proc = ChannelProcess(layout, CHAN_ID, "host")
            self.assertIsNone(proc._credential)
        finally:
            shutil.rmtree(tmp)


class TestBlackboard(unittest.TestCase):

    def setUp(self):
        self.layout, self.tmp = _make_layout_with_cmi()
        self.proc = _make_process(self.layout)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_append_and_read(self):
        entry = {"seq": 1, "from": "sha256:abc", "content": "hello", "ts": 0}
        self.proc._append_bb(entry)
        entries = self.proc._read_bb()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["content"], "hello")

    def test_multiple_entries_ordered(self):
        for i in range(3):
            self.proc._append_bb({"seq": i + 1, "from": "x", "content": str(i), "ts": i})
        entries = self.proc._read_bb()
        self.assertEqual(len(entries), 3)
        self.assertEqual([e["seq"] for e in entries], [1, 2, 3])

    def test_empty_bb_returns_empty_list(self):
        entries = self.proc._read_bb()
        self.assertEqual(entries, [])

    def test_archive_bb_creates_archive_json(self):
        self.proc._append_bb({"seq": 1, "from": "x", "content": "data", "ts": 0})
        self.proc._archive_bb()
        archive_path = self.layout.cmi_channel_dir(CHAN_ID) / "archive.json"
        self.assertTrue(archive_path.exists())
        data = read_json(archive_path)
        self.assertEqual(data["chan_id"], CHAN_ID)
        self.assertEqual(data["entry_count"], 1)
        self.assertIn("bb_digest", data)

    def test_archive_bb_empty_channel(self):
        self.proc._archive_bb()
        archive_path = self.layout.cmi_channel_dir(CHAN_ID) / "archive.json"
        self.assertTrue(archive_path.exists())
        data = read_json(archive_path)
        self.assertEqual(data["entry_count"], 0)


class TestParticipantsPersistence(unittest.TestCase):

    def setUp(self):
        self.layout, self.tmp = _make_layout_with_cmi()
        self.proc = _make_process(self.layout)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_save_participants_writes_file(self):
        self.proc._enrolled_peers = [{
            "node_identity": "sha256:peer1", "endpoint": "http://x:7700",
            "pubkey": "aabb", "role": "peer",
        }]
        self.proc._save_participants()
        p = read_json(self.layout.cmi_participants(CHAN_ID))
        self.assertEqual(p["local_role"], "host")
        self.assertEqual(len(p["peers"]), 1)
        self.assertEqual(p["peers"][0]["node_identity"], "sha256:peer1")

    def test_update_participants_status(self):
        self.proc._update_participants_status("active")
        p = read_json(self.layout.cmi_participants(CHAN_ID))
        self.assertEqual(p["status"], "active")

        self.proc._update_participants_status("closed")
        p2 = read_json(self.layout.cmi_participants(CHAN_ID))
        self.assertEqual(p2["status"], "closed")

    def test_update_participants_preserves_peers(self):
        self.proc._enrolled_peers = [{"node_identity": "sha256:x", "role": "peer"}]
        self.proc._save_participants()
        self.proc._update_participants_status("closing")
        p = read_json(self.layout.cmi_participants(CHAN_ID))
        # peers field preserved across status update
        self.assertEqual(len(p["peers"]), 1)


class TestChannelStatus(unittest.TestCase):

    def setUp(self):
        self.layout, self.tmp = _make_layout_with_cmi()
        self.proc = _make_process(self.layout)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_update_channel_status_in_baseline(self):
        self.proc._update_channel_status("active")
        baseline = read_json(self.layout.baseline)
        ch = next(c for c in baseline["cmi"]["channels"] if c["id"] == CHAN_ID)
        self.assertEqual(ch["status"], "active")

    def test_update_to_closing_then_closed(self):
        self.proc._update_channel_status("closing")
        self.proc._update_channel_status("closed")
        baseline = read_json(self.layout.baseline)
        ch = next(c for c in baseline["cmi"]["channels"] if c["id"] == CHAN_ID)
        self.assertEqual(ch["status"], "closed")


class TestInboxStimulus(unittest.TestCase):

    def setUp(self):
        self.layout, self.tmp = _make_layout_with_cmi()
        self.proc = _make_process(self.layout)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_msg_general_written_to_inbox(self):
        self.proc._write_inbox_stimulus("CMI_MSG_GENERAL", {
            "content": "hello from peer",
            "from": "sha256:abc",
        })
        files = list(self.layout.inbox_dir.iterdir())
        self.assertGreater(len(files), 0)
        found = [f for f in files if "cmi_msg_general" in f.name]
        self.assertEqual(len(found), 1)
        data = _read_inbox_data(found[0])
        self.assertEqual(data["type"], "CMI_MSG_GENERAL")
        self.assertEqual(data["channel_id"], CHAN_ID)
        self.assertEqual(data["content"], "hello from peer")

    def test_msg_peer_written_to_inbox(self):
        self.proc._write_inbox_stimulus("CMI_MSG_PEER", {
            "content": "hey alice",
            "from": "sha256:bob",
            "to": "sha256:alice",
        })
        found = [f for f in self.layout.inbox_dir.iterdir()
                 if "cmi_msg_peer" in f.name]
        self.assertEqual(len(found), 1)
        data = _read_inbox_data(found[0])
        self.assertEqual(data["type"], "CMI_MSG_PEER")
        self.assertEqual(data["to"], "sha256:alice")

    def test_msg_bb_written_to_inbox(self):
        self.proc._write_inbox_stimulus("CMI_MSG_BB", {
            "seq": 5,
            "from": "sha256:peer",
            "content": "my contribution",
        })
        files = [f for f in self.layout.inbox_dir.iterdir()
                 if "cmi_msg_bb" in f.name]
        self.assertEqual(len(files), 1)
        data = _read_inbox_data(files[0])
        self.assertEqual(data["seq"], 5)
        self.assertEqual(data["type"], "CMI_MSG_BB")


class TestHandleMessage(unittest.TestCase):
    """Test _handle_message — ephemeral msg:general and msg:peer."""

    class _FakeHandler:
        """Minimal stand-in for the HTTP handler passed to _handle_message."""
        def __init__(self):
            self.response = None
            self.error = None

        def _ok(self, data):
            self.response = data

        def _bad_request(self, msg):
            self.error = ("bad_request", msg)

        def _forbidden(self, msg):
            self.error = ("forbidden", msg)

    def setUp(self):
        self.layout, self.tmp = _make_layout_with_cmi()
        self.proc = _make_process(self.layout)
        # Enroll a fake peer
        self.peer_ni = "sha256:" + "a" * 62 + "00"
        self.peer_privkey = "b" * 64
        self.proc._enrolled_peers = [{
            "node_identity": self.peer_ni,
            "endpoint": "http://peer:7700",
            "pubkey": self.peer_privkey,  # PSK: pubkey == privkey for verify
            "role": "peer",
        }]

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _make_payload(self, msg_type, content, to=None):
        from fcp_core.cmi.identity import sign_message
        payload = {
            "type": msg_type,
            "from": self.peer_ni,
            "content": content,
        }
        if to:
            payload["to"] = to
        check = {k: v for k, v in payload.items()}
        data = json.dumps(check, sort_keys=True).encode()
        payload["sig"] = sign_message(self.peer_privkey, data)
        return payload

    def test_msg_general_accepted(self):
        handler = self._FakeHandler()
        payload = self._make_payload("msg:general", "hello everyone")
        self.proc._handle_message(handler, payload)
        self.assertIsNone(handler.error)
        self.assertEqual(handler.response, {"received": True})

    def test_msg_general_written_to_inbox(self):
        handler = self._FakeHandler()
        payload = self._make_payload("msg:general", "broadcast msg")
        self.proc._handle_message(handler, payload)
        found = [f for f in self.layout.inbox_dir.iterdir()
                 if "cmi_msg_general" in f.name]
        self.assertEqual(len(found), 1)
        data = _read_inbox_data(found[0])
        self.assertEqual(data["type"], "CMI_MSG_GENERAL")

    def test_msg_peer_accepted_with_to(self):
        handler = self._FakeHandler()
        target_ni = "sha256:" + "b" * 62 + "00"
        payload = self._make_payload("msg:peer", "hey alice", to=target_ni)
        self.proc._handle_message(handler, payload)
        self.assertIsNone(handler.error)

    def test_msg_peer_written_to_inbox_with_to_field(self):
        handler = self._FakeHandler()
        target_ni = "sha256:" + "c" * 62 + "00"
        payload = self._make_payload("msg:peer", "addressed msg", to=target_ni)
        self.proc._handle_message(handler, payload)
        found = [f for f in self.layout.inbox_dir.iterdir()
                 if "cmi_msg_peer" in f.name]
        self.assertEqual(len(found), 1)
        data = _read_inbox_data(found[0])
        self.assertEqual(data["to"], target_ni)

    def test_msg_peer_without_to_rejected(self):
        handler = self._FakeHandler()
        payload = self._make_payload("msg:peer", "missing to")
        # Remove 'to' from payload manually
        payload.pop("to", None)
        self.proc._handle_message(handler, payload)
        self.assertIsNotNone(handler.error)
        self.assertEqual(handler.error[0], "bad_request")

    def test_invalid_type_rejected(self):
        handler = self._FakeHandler()
        payload = self._make_payload("msg:general", "test")
        payload["type"] = "msg:bb"  # wrong endpoint
        self.proc._handle_message(handler, payload)
        self.assertIsNotNone(handler.error)
        self.assertEqual(handler.error[0], "bad_request")

    def test_non_enrolled_sender_rejected(self):
        handler = self._FakeHandler()
        payload = {
            "type": "msg:general",
            "from": "sha256:" + "f" * 64,
            "content": "intruder",
            "sig": "fakesig",
        }
        self.proc._handle_message(handler, payload)
        self.assertIsNotNone(handler.error)
        self.assertEqual(handler.error[0], "forbidden")

    def test_non_host_role_rejected(self):
        layout, tmp = _make_layout_with_cmi(role="peer")
        try:
            proc = _make_process(layout, role="peer")
            handler = self._FakeHandler()
            payload = {"type": "msg:general", "from": "x", "content": "test", "sig": ""}
            proc._handle_message(handler, payload)
            self.assertEqual(handler.error[0], "forbidden")
        finally:
            shutil.rmtree(tmp)


class TestMifLogging(unittest.TestCase):

    def setUp(self):
        self.layout, self.tmp = _make_layout_with_cmi()
        self.proc = _make_process(self.layout)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_mif_logged_to_integrity_log(self):
        self.proc._log_mif("MIF-AUTH", "authentication failure from peer x")
        entries = read_jsonl(self.layout.integrity_log)
        mif_entries = []
        for e in entries:
            raw = e.get("data", "{}")
            data = json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(data, dict) and data.get("type") == "MESH_INTEGRITY_FAULT":
                mif_entries.append(data)
        self.assertEqual(len(mif_entries), 1)
        self.assertEqual(mif_entries[0]["code"], "MIF-AUTH")
        self.assertEqual(mif_entries[0]["chan_id"], CHAN_ID)

    def test_mif_codes_logged_correctly(self):
        codes = ["MIF-BB-SEQ", "MIF-AUTH", "MIF-ROLE", "MIF-HOST", "MIF-ENROLL"]
        for code in codes:
            self.proc._log_mif(code, f"test {code}")
        entries = read_jsonl(self.layout.integrity_log)
        logged_codes = []
        for e in entries:
            raw = e.get("data", "{}")
            data = json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(data, dict) and data.get("type") == "MESH_INTEGRITY_FAULT":
                logged_codes.append(data["code"])
        self.assertEqual(logged_codes, codes)


class TestTrustedPeerLookup(unittest.TestCase):

    def setUp(self):
        self.layout, self.tmp = _make_layout_with_cmi()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_find_existing_peer(self):
        baseline = read_json(self.layout.baseline)
        baseline["cmi"]["trusted_peers"] = [{
            "node_identity": "sha256:peer1",
            "endpoint": "http://peer:7700",
            "trust_label": "FULL",
            "alias": "bob",
            "pubkey": "deadbeef",
        }]
        atomic_write(self.layout.baseline, baseline)

        proc = _make_process(self.layout)
        peer = proc._find_trusted_peer("sha256:peer1")
        self.assertIsNotNone(peer)
        self.assertEqual(peer["alias"], "bob")

    def test_find_nonexistent_peer_returns_none(self):
        proc = _make_process(self.layout)
        self.assertIsNone(proc._find_trusted_peer("sha256:unknown"))


class TestSignVerifyIntegration(unittest.TestCase):
    """Verify that ChannelProcess signing integrates with identity module."""

    def setUp(self):
        self.layout, self.tmp = _make_layout_with_cmi()
        self.proc = _make_process(self.layout)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_verify_own_signature(self):
        from fcp_core.cmi.identity import sign_message
        cred = self.proc._credential
        payload = {"type": "test", "content": "hello"}
        data = json.dumps(payload, sort_keys=True).encode()
        sig = sign_message(cred["privkey"], data)
        # verify using privkey (PSK model)
        result = self.proc._verify(cred["privkey"], payload, sig)
        self.assertTrue(result)

    def test_verify_wrong_key_fails(self):
        from fcp_core.cmi.identity import sign_message
        cred = self.proc._credential
        payload = {"type": "test", "content": "hello"}
        data = json.dumps(payload, sort_keys=True).encode()
        sig = sign_message(cred["privkey"], data)
        # verify with wrong key
        result = self.proc._verify("0" * 64, payload, sig)
        self.assertFalse(result)

    def test_verify_empty_pubkey_fails(self):
        result = self.proc._verify("", {"x": 1}, "somesig")
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
