"""Tests for fcp_base.cmi.identity — Node Identity and CMI Credential."""

import json
import os
import tempfile
import unittest
from pathlib import Path

from fcp_base.store import Layout, atomic_write
from fcp_base.cmi.identity import (
    derive_node_identity,
    read_genesis_omega,
    generate_cmi_credential,
    rotate_cmi_credential,
    load_cmi_credential,
    sign_message,
    verify_signature,
)


def _make_layout_with_genesis(tmp: str, genesis_omega: str = "abc123") -> Layout:
    """Create a Layout with a minimal integrity_chain.jsonl containing a GENESIS entry."""
    layout = Layout(Path(tmp))
    os.makedirs(layout.state_dir, exist_ok=True)
    genesis_entry = json.dumps({
        "seq": 1,
        "type": "GENESIS",
        "ts": "2026-01-01T00:00:00Z",
        "imprint_hash": genesis_omega,
    })
    layout.integrity_chain.write_text(genesis_entry + "\n", encoding="utf-8")
    return layout


class TestDeriveNodeIdentity(unittest.TestCase):

    def test_deterministic(self):
        ni1 = derive_node_identity("deadbeef")
        ni2 = derive_node_identity("deadbeef")
        self.assertEqual(ni1, ni2)

    def test_prefix(self):
        ni = derive_node_identity("deadbeef")
        self.assertTrue(ni.startswith("sha256:"))

    def test_strips_sha256_prefix(self):
        raw = derive_node_identity("deadbeef")
        prefixed = derive_node_identity("sha256:deadbeef")
        self.assertEqual(raw, prefixed)

    def test_different_inputs_differ(self):
        self.assertNotEqual(
            derive_node_identity("aaa"),
            derive_node_identity("bbb"),
        )


class TestReadGenesisOmega(unittest.TestCase):

    def test_reads_from_chain(self):
        with tempfile.TemporaryDirectory() as tmp:
            layout = _make_layout_with_genesis(tmp, "myhash123")
            result = read_genesis_omega(layout)
            self.assertEqual(result, "myhash123")

    def test_missing_chain_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            layout = Layout(Path(tmp))
            os.makedirs(layout.state_dir, exist_ok=True)
            with self.assertRaises(RuntimeError):
                read_genesis_omega(layout)

    def test_missing_genesis_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            layout = Layout(Path(tmp))
            os.makedirs(layout.state_dir, exist_ok=True)
            # Write a chain with no GENESIS entry
            layout.integrity_chain.write_text(
                json.dumps({"seq": 2, "type": "HEARTBEAT", "ts": "x"}) + "\n",
                encoding="utf-8",
            )
            with self.assertRaises(RuntimeError):
                read_genesis_omega(layout)

    def test_genesis_with_sha256_prefix(self):
        with tempfile.TemporaryDirectory() as tmp:
            layout = _make_layout_with_genesis(tmp, "sha256:cafebabe")
            result = read_genesis_omega(layout)
            self.assertEqual(result, "sha256:cafebabe")


class TestGenerateCredential(unittest.TestCase):

    def test_generates_and_persists(self):
        with tempfile.TemporaryDirectory() as tmp:
            layout = _make_layout_with_genesis(tmp, "genesis1")
            cred = generate_cmi_credential(layout)
            self.assertIn("node_identity", cred)
            self.assertIn("privkey", cred)
            self.assertIn("pubkey", cred)
            self.assertIn("created_at", cred)
            self.assertTrue(layout.cmi_credential.exists())

    def test_node_identity_derived_from_genesis(self):
        with tempfile.TemporaryDirectory() as tmp:
            layout = _make_layout_with_genesis(tmp, "genesis1")
            cred = generate_cmi_credential(layout)
            expected_ni = derive_node_identity("genesis1")
            self.assertEqual(cred["node_identity"], expected_ni)

    def test_duplicate_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            layout = _make_layout_with_genesis(tmp, "genesis1")
            generate_cmi_credential(layout)
            with self.assertRaises(RuntimeError):
                generate_cmi_credential(layout)

    def test_privkey_pubkey_differ(self):
        with tempfile.TemporaryDirectory() as tmp:
            layout = _make_layout_with_genesis(tmp, "genesis1")
            cred = generate_cmi_credential(layout)
            self.assertNotEqual(cred["privkey"], cred["pubkey"])

    def test_two_entities_get_different_keys(self):
        with tempfile.TemporaryDirectory() as tmp1, tempfile.TemporaryDirectory() as tmp2:
            l1 = _make_layout_with_genesis(tmp1, "genesis1")
            l2 = _make_layout_with_genesis(tmp2, "genesis2")
            c1 = generate_cmi_credential(l1)
            c2 = generate_cmi_credential(l2)
            self.assertNotEqual(c1["privkey"], c2["privkey"])
            self.assertNotEqual(c1["pubkey"], c2["pubkey"])
            self.assertNotEqual(c1["node_identity"], c2["node_identity"])


class TestRotateCredential(unittest.TestCase):

    def test_rotate_changes_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            layout = _make_layout_with_genesis(tmp, "genesis1")
            c1 = generate_cmi_credential(layout)
            c2 = rotate_cmi_credential(layout)
            self.assertNotEqual(c1["privkey"], c2["privkey"])
            self.assertNotEqual(c1["pubkey"], c2["pubkey"])

    def test_rotate_preserves_node_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            layout = _make_layout_with_genesis(tmp, "genesis1")
            c1 = generate_cmi_credential(layout)
            c2 = rotate_cmi_credential(layout)
            self.assertEqual(c1["node_identity"], c2["node_identity"])

    def test_rotate_without_existing_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            layout = _make_layout_with_genesis(tmp, "genesis1")
            with self.assertRaises(RuntimeError):
                rotate_cmi_credential(layout)


class TestLoadCredential(unittest.TestCase):

    def test_returns_none_when_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            layout = Layout(Path(tmp))
            self.assertIsNone(load_cmi_credential(layout))

    def test_returns_dict_when_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            layout = _make_layout_with_genesis(tmp, "genesis1")
            generate_cmi_credential(layout)
            cred = load_cmi_credential(layout)
            self.assertIsNotNone(cred)
            self.assertIn("node_identity", cred)


class TestSignVerify(unittest.TestCase):

    def _keypair(self):
        with tempfile.TemporaryDirectory() as tmp:
            layout = _make_layout_with_genesis(tmp, "genesis1")
            cred = generate_cmi_credential(layout)
            return cred["privkey"], cred["pubkey"]

    def test_valid_signature(self):
        priv, _pub = self._keypair()
        data = b"hello world"
        sig = sign_message(priv, data)
        # PSK model: verifier uses the same privkey
        self.assertTrue(verify_signature(priv, data, sig))

    def test_wrong_data_fails(self):
        priv, _pub = self._keypair()
        sig = sign_message(priv, b"correct data")
        self.assertFalse(verify_signature(priv, b"wrong data", sig))

    def test_wrong_key_fails(self):
        priv, _pub = self._keypair()
        priv2, _pub2 = self._keypair()  # different keypair
        sig = sign_message(priv, b"data")
        self.assertFalse(verify_signature(priv2, b"data", sig))

    def test_tampered_sig_fails(self):
        priv, _pub = self._keypair()
        sig = sign_message(priv, b"data")
        tampered = sig[:-4] + "0000"
        self.assertFalse(verify_signature(priv, b"data", tampered))

    def test_empty_data(self):
        priv, _pub = self._keypair()
        sig = sign_message(priv, b"")
        self.assertTrue(verify_signature(priv, b"", sig))

    def test_sign_is_deterministic(self):
        priv, _ = self._keypair()
        data = b"test"
        self.assertEqual(sign_message(priv, data), sign_message(priv, data))


if __name__ == "__main__":
    unittest.main()
