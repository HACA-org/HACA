"""
SIL utilities — hashing and timestamp helpers.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path


def utcnow() -> str:
    """Return current UTC time as 'YYYY-MM-DDTHH:MM:SSZ'."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path: Path) -> str:
    """Return 'sha256:<hex>' digest of *path* contents."""
    h = hashlib.sha256(path.read_bytes())
    return f"sha256:{h.hexdigest()}"


def sha256_str(text: str) -> str:
    """Return 'sha256:<hex>' digest of *text* encoded as UTF-8."""
    h = hashlib.sha256(text.encode())
    return f"sha256:{h.hexdigest()}"


def sha256_bytes(data: bytes) -> str:
    """Return 'sha256:<hex>' digest of raw bytes."""
    return f"sha256:{hashlib.sha256(data).hexdigest()}"
