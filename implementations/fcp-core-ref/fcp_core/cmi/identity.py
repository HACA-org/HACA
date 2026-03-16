"""
CMI Identity — Node Identity and CMI Credential.

Node Identity (Π):
    sha256(genesis_omega + "cmi-node"), hex-encoded with "sha256:" prefix.
    Permanent — derived from the Genesis Omega, never changes.

CMI Credential (K_cmi):
    HMAC-SHA256 pre-shared key scheme (stdlib-only; Ed25519 is a future TODO).

    privkey = 32 random bytes (hex) — the HMAC secret key, never shared.
    pubkey  = sha256(privkey) (hex) — public identifier, shared with peers.

    Signing:   HMAC-SHA256(privkey, data)
    Verifying: the verifier needs the privkey (PSK model). In HACA-Core this
               is acceptable because all peers are Operator-pre-approved and
               keys are exchanged out-of-band via the Endure Protocol.

    Credential file schema:
    {
      "node_identity": "sha256:...",
      "privkey": "<hex>",
      "pubkey":  "<hex>",
      "created_at": "2026-..."
    }

TODO (production): replace with Ed25519 via cryptography or PyNaCl — true
asymmetric signing where pubkey is sufficient for verification.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..store import Layout


# ---------------------------------------------------------------------------
# Node Identity
# ---------------------------------------------------------------------------

def derive_node_identity(genesis_omega: str) -> str:
    """Derive Π from the Genesis Omega.

    genesis_omega may carry a "sha256:" prefix (as stored in the chain) or be
    a raw hex string — both are handled.
    """
    raw = genesis_omega.removeprefix("sha256:")
    digest = hashlib.sha256((raw + "cmi-node").encode()).hexdigest()
    return f"sha256:{digest}"


def read_genesis_omega(layout: "Layout") -> str:
    """Read the Genesis Omega (imprint_hash of seq=1) from integrity_chain.jsonl.

    Raises RuntimeError if the chain is absent or GENESIS entry is missing.
    """
    import json
    if not layout.integrity_chain.exists():
        raise RuntimeError("integrity_chain.jsonl not found — entity not initialized")
    for line in layout.integrity_chain.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        entry = json.loads(line)
        if entry.get("seq") == 1 and entry.get("type") == "GENESIS":
            ih = entry.get("imprint_hash")
            if not ih:
                raise RuntimeError("GENESIS entry has no imprint_hash")
            return ih
    raise RuntimeError("GENESIS entry not found in integrity_chain.jsonl")


# ---------------------------------------------------------------------------
# CMI Credential
# ---------------------------------------------------------------------------

def generate_cmi_credential(layout: "Layout") -> dict:
    """Generate and persist a new CMI Credential.

    Reads the Genesis Omega to derive the Node Identity, generates a fresh
    secret, derives privkey and pubkey, writes credential.json atomically.

    Returns the credential dict (same structure as the file).
    Raises RuntimeError if credential already exists (rotation must use
    rotate_cmi_credential instead).
    """
    from ..store import atomic_write

    if layout.cmi_credential.exists():
        raise RuntimeError(
            "CMI Credential already exists. Use rotate_cmi_credential() to rotate."
        )

    genesis_omega = read_genesis_omega(layout)
    node_identity = derive_node_identity(genesis_omega)

    privkey = secrets.token_hex(32)
    pubkey = hashlib.sha256(privkey.encode()).hexdigest()

    credential = {
        "node_identity": node_identity,
        "privkey": privkey,
        "pubkey": pubkey,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    layout.cmi_dir.mkdir(parents=True, exist_ok=True)
    atomic_write(layout.cmi_credential, credential)
    return credential


def rotate_cmi_credential(layout: "Layout") -> dict:
    """Rotate the CMI Credential: generate a new one, preserve node_identity.

    Returns the new credential dict.
    Raises RuntimeError if no credential exists yet.
    """
    from ..store import atomic_write, read_json

    if not layout.cmi_credential.exists():
        raise RuntimeError(
            "No CMI Credential to rotate. Use generate_cmi_credential() first."
        )

    existing = read_json(layout.cmi_credential)
    node_identity = existing["node_identity"]

    privkey = secrets.token_hex(32)
    pubkey = hashlib.sha256(privkey.encode()).hexdigest()

    credential = {
        "node_identity": node_identity,
        "privkey": privkey,
        "pubkey": pubkey,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    atomic_write(layout.cmi_credential, credential)
    return credential


def load_cmi_credential(layout: "Layout") -> dict | None:
    """Read credential.json, returning None if absent or unreadable."""
    from ..store import read_json
    try:
        return read_json(layout.cmi_credential)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Signing and verification
# ---------------------------------------------------------------------------

def sign_message(privkey_hex: str, data: bytes) -> str:
    """Sign *data* with privkey_hex using HMAC-SHA256. Returns hex digest."""
    key = bytes.fromhex(privkey_hex)
    return hmac.new(key, data, hashlib.sha256).hexdigest()


def verify_signature(privkey_hex: str, data: bytes, sig_hex: str) -> bool:
    """Verify HMAC-SHA256 *sig_hex* over *data* using privkey_hex.

    PSK model: the verifier must possess the signer's privkey, exchanged
    out-of-band via the Endure Protocol.  Returns True on match, False on
    any mismatch or error.
    """
    try:
        key = bytes.fromhex(privkey_hex)
        expected = hmac.new(key, data, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, sig_hex)
    except Exception:
        return False
