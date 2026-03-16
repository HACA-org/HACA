"""Tests for the cmi_peer_add Endure op in sleep._stage3_endure."""

import json
import shutil
import unittest

from fcp_core import sleep as sleep_mod
from fcp_core.store import Layout, atomic_write, append_jsonl, read_json
from tests.helpers import make_layout


def _inject_evolution_auth(layout: Layout, content: dict) -> None:
    """Write a minimal EVOLUTION_AUTH record to integrity.log (after a SLEEP_COMPLETE)."""
    # First write SLEEP_COMPLETE so the collector finds proposals after it
    from fcp_core.acp import make as acp_encode
    sleep_entry = acp_encode(
        env_type="MSG",
        source="sil",
        data={"type": "SLEEP_COMPLETE", "ts": 0},
    )
    append_jsonl(layout.integrity_log, sleep_entry)

    auth_entry = acp_encode(
        env_type="MSG",
        source="sil",
        data={
            "type": "EVOLUTION_AUTH",
            "auth_digest": "testdigest",
            "content": json.dumps({"changes": [content]}),
            "slugs": [],
        },
    )
    append_jsonl(layout.integrity_log, auth_entry)


VALID_PEER = {
    "op": "cmi_peer_add",
    "node_identity": "sha256:abc123def456abc123def456abc123def456abc123def456abc123def456abc1",
    "endpoint": "http://192.168.1.10:7700",
    "trust_label": "FULL",
    "alias": "alice",
    "pubkey": "deadbeef" * 8,
}


class TestCmiPeerAdd(unittest.TestCase):

    def setUp(self) -> None:
        self.layout, self.tmp = make_layout()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def test_peer_added_to_baseline(self):
        _inject_evolution_auth(self.layout, VALID_PEER)
        sleep_mod._stage3_endure(self.layout)

        baseline = read_json(self.layout.baseline)
        peers = baseline.get("cmi", {}).get("trusted_peers", [])
        self.assertEqual(len(peers), 1)
        self.assertEqual(peers[0]["alias"], "alice")
        self.assertEqual(peers[0]["trust_label"], "FULL")
        self.assertEqual(peers[0]["node_identity"], VALID_PEER["node_identity"])

    def test_peer_pubkey_stored(self):
        _inject_evolution_auth(self.layout, VALID_PEER)
        sleep_mod._stage3_endure(self.layout)

        baseline = read_json(self.layout.baseline)
        peers = baseline["cmi"]["trusted_peers"]
        self.assertEqual(peers[0]["pubkey"], VALID_PEER["pubkey"])

    def test_duplicate_peer_replaced(self):
        """Adding same node_identity twice replaces the existing entry."""
        _inject_evolution_auth(self.layout, VALID_PEER)
        sleep_mod._stage3_endure(self.layout)

        updated = dict(VALID_PEER)
        updated["trust_label"] = "CONTACT"
        updated["alias"] = "alice-updated"
        _inject_evolution_auth(self.layout, updated)
        sleep_mod._stage3_endure(self.layout)

        baseline = read_json(self.layout.baseline)
        peers = baseline["cmi"]["trusted_peers"]
        self.assertEqual(len(peers), 1)
        self.assertEqual(peers[0]["trust_label"], "CONTACT")
        self.assertEqual(peers[0]["alias"], "alice-updated")

    def test_notification_written(self):
        _inject_evolution_auth(self.layout, VALID_PEER)
        sleep_mod._stage3_endure(self.layout)

        notifs = list(self.layout.operator_notifications_dir.iterdir())
        self.assertGreater(len(notifs), 0)
        found = any("cmi_peer_added" in f.name for f in notifs)
        self.assertTrue(found, "Expected cmi_peer_added notification")

    def test_baseline_tracked_in_integrity_doc(self):
        _inject_evolution_auth(self.layout, VALID_PEER)
        sleep_mod._stage3_endure(self.layout)

        doc = read_json(self.layout.integrity_doc)
        self.assertIn("state/baseline.json", doc.get("files", {}))

    def test_invalid_trust_label_rejected(self):
        bad = dict(VALID_PEER)
        bad["trust_label"] = "UNKNOWN"
        _inject_evolution_auth(self.layout, bad)
        sleep_mod._stage3_endure(self.layout)

        baseline = read_json(self.layout.baseline)
        peers = baseline.get("cmi", {}).get("trusted_peers", [])
        self.assertEqual(peers, [])

    def test_missing_node_identity_rejected(self):
        bad = {k: v for k, v in VALID_PEER.items() if k != "node_identity"}
        _inject_evolution_auth(self.layout, bad)
        sleep_mod._stage3_endure(self.layout)

        baseline = read_json(self.layout.baseline)
        peers = baseline.get("cmi", {}).get("trusted_peers", [])
        self.assertEqual(peers, [])

    def test_node_identity_without_prefix_rejected(self):
        bad = dict(VALID_PEER)
        bad["node_identity"] = "abc123"  # missing "sha256:" prefix
        _inject_evolution_auth(self.layout, bad)
        sleep_mod._stage3_endure(self.layout)

        baseline = read_json(self.layout.baseline)
        peers = baseline.get("cmi", {}).get("trusted_peers", [])
        self.assertEqual(peers, [])

    def test_missing_endpoint_rejected(self):
        bad = {k: v for k, v in VALID_PEER.items() if k != "endpoint"}
        _inject_evolution_auth(self.layout, bad)
        sleep_mod._stage3_endure(self.layout)

        baseline = read_json(self.layout.baseline)
        peers = baseline.get("cmi", {}).get("trusted_peers", [])
        self.assertEqual(peers, [])

    def test_all_three_trust_labels_accepted(self):
        for label in ("FULL", "CONTACT", "INTRODUCED"):
            layout, tmp = make_layout()
            try:
                peer = dict(VALID_PEER)
                peer["trust_label"] = label
                _inject_evolution_auth(layout, peer)
                sleep_mod._stage3_endure(layout)
                baseline = read_json(layout.baseline)
                peers = baseline.get("cmi", {}).get("trusted_peers", [])
                self.assertEqual(len(peers), 1, f"Expected 1 peer for label {label}")
                self.assertEqual(peers[0]["trust_label"], label)
            finally:
                shutil.rmtree(tmp)


if __name__ == "__main__":
    unittest.main()
