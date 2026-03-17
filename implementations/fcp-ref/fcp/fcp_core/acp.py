"""
ACP — Atomic Chunked Protocol.  §3.1

Responsibilities:
  - ACPEnvelope dataclass
  - CRC-32/ISO-HDLC computation
  - encode / decode (single envelope ↔ JSON line)
  - chunk  (large payload → list[ACPEnvelope])
  - spool_write / drain_inbox  (io/ filesystem I/O)

Reassembly of multi-chunk transactions is stateful and belongs in the
session loop, not here.  drain_inbox returns individual envelopes in
timestamp order.
"""

from __future__ import annotations

import json
import os
import uuid
import zlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Maximum encoded envelope size in bytes (UTF-8).
_ENVELOPE_LIMIT = 4000

# Suffix used for messages written to inbox/.
_MSG_SUFFIX = ".msg"


# ---------------------------------------------------------------------------
# Envelope
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class ACPEnvelope:
    actor: str
    gseq:  int
    tx:    str
    seq:   int
    eof:   bool
    type:  str
    ts:    str      # ISO 8601 UTC
    data:  str
    crc:   str      # 8-char lowercase hex

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ACPEnvelope:
        return cls(
            actor=d["actor"],
            gseq=d["gseq"],
            tx=d["tx"],
            seq=d["seq"],
            eof=d["eof"],
            type=d["type"],
            ts=d["ts"],
            data=d["data"],
            crc=d["crc"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "actor": self.actor,
            "gseq":  self.gseq,
            "tx":    self.tx,
            "seq":   self.seq,
            "eof":   self.eof,
            "type":  self.type,
            "ts":    self.ts,
            "data":  self.data,
            "crc":   self.crc,
        }


# ---------------------------------------------------------------------------
# CRC-32/ISO-HDLC
# ---------------------------------------------------------------------------

def crc32(data: str) -> str:
    """Return CRC-32/ISO-HDLC of *data* as 8-character lowercase hex.

    zlib.crc32 implements exactly this variant:
      polynomial 0xEDB88320, init 0xFFFFFFFF, final XOR 0xFFFFFFFF.
    The result is masked to unsigned 32-bit before formatting.
    """
    value = zlib.crc32(data.encode()) & 0xFFFFFFFF
    return f"{value:08x}"


# ---------------------------------------------------------------------------
# Encode / decode
# ---------------------------------------------------------------------------

def encode(env: ACPEnvelope) -> str:
    """Serialise *env* to a single JSON line (no trailing newline)."""
    return json.dumps(env.to_dict(), separators=(",", ":"))


_gseq: dict[str, int] = {}


def make(*, env_type: str, source: str, data: Any) -> dict[str, Any]:
    """Factory: build a single-frame envelope dict from high-level kwargs.

    *data* may be any JSON-serialisable value; it is serialised to a string
    before being stored in the ``data`` field.
    Returns a plain dict suitable for ``append_jsonl`` / ``atomic_write``.
    """
    global _gseq
    seq = _gseq.get(source, 0)
    _gseq[source] = seq + 1
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    tx = str(uuid.uuid4())
    payload = data if isinstance(data, str) else json.dumps(data, separators=(",", ":"))
    return {
        "actor": source,
        "gseq": seq,
        "tx": tx,
        "seq": 1,
        "eof": True,
        "type": env_type,
        "ts": ts,
        "data": payload,
        "crc": crc32(payload),
    }


def decode(line: str) -> ACPEnvelope:
    """Deserialise a JSON line to ACPEnvelope and validate CRC.

    Raises ValueError if the line is malformed or the CRC does not match.
    """
    try:
        d = json.loads(line)
    except json.JSONDecodeError as exc:
        raise ValueError(f"acp.decode: invalid JSON — {exc}") from exc

    env = ACPEnvelope.from_dict(d)
    expected = crc32(env.data)
    if env.crc != expected:
        raise ValueError(
            f"acp.decode: CRC mismatch for tx={env.tx} seq={env.seq} "
            f"(got {env.crc!r}, expected {expected!r})"
        )
    return env


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def chunk(
    actor: str,
    type_: str,
    data: str,
    gseq_counter: list[int],
    tx: str | None = None,
) -> list[ACPEnvelope]:
    """Split *data* into one or more ACPEnvelopes that each fit within
    _ENVELOPE_LIMIT bytes when encoded.

    *gseq_counter* must be a one-element list holding the current gseq value
    for *actor*.  It is incremented in-place for each envelope produced.

    *tx* is generated automatically when not provided.
    """
    tx_id = tx or str(uuid.uuid4())
    ts = _utcnow()

    # Split data into chunks sized so that the full encoded envelope stays
    # under _ENVELOPE_LIMIT.  We compute the overhead by encoding a probe
    # envelope with an empty data field, then derive the usable data budget.
    probe = ACPEnvelope(
        actor=actor, gseq=0, tx=tx_id, seq=1, eof=True,
        type=type_, ts=ts, data="", crc=crc32(""),
    )
    overhead = len(encode(probe).encode())
    budget = _ENVELOPE_LIMIT - overhead
    if budget <= 0:
        raise ValueError("acp.chunk: envelope overhead exceeds size limit")

    # Split the raw data string by byte budget (UTF-8 aware).
    raw: bytes = data.encode()
    parts: list[str] = []
    offset = 0
    total = len(raw)
    while offset < total:
        end = min(offset + budget, total)
        # Walk back to a valid UTF-8 boundary.
        while end > offset:
            try:
                part = raw[offset:end].decode()
                break
            except UnicodeDecodeError:
                end -= 1
        else:
            raise ValueError("acp.chunk: cannot decode a single byte as UTF-8")
        parts.append(part)
        offset = end

    if not parts:
        parts = [""]

    envelopes: list[ACPEnvelope] = []
    for i, part in enumerate(parts):
        gseq_counter[0] += 1
        envelopes.append(ACPEnvelope(
            actor=actor,
            gseq=gseq_counter[0],
            tx=tx_id,
            seq=i + 1,
            eof=(i == len(parts) - 1),
            type=type_,
            ts=ts,
            data=part,
            crc=crc32(part),
        ))

    return envelopes


# ---------------------------------------------------------------------------
# IO — spool / drain
# ---------------------------------------------------------------------------

def spool_write(spool_dir: Path, inbox_dir: Path, env: ACPEnvelope) -> None:
    """Write *env* atomically into *inbox_dir* via *spool_dir*.

    Uses spool-then-rename: write to spool/ with a unique name, then
    os.rename into inbox/.  os.rename is atomic on POSIX when src and dst
    are on the same filesystem.
    """
    name = f"{env.ts}_{env.tx}_{env.seq:04d}{_MSG_SUFFIX}"
    spool_path = spool_dir / name
    inbox_path = inbox_dir / name

    spool_path.write_text(encode(env), encoding="utf-8")
    os.rename(spool_path, inbox_path)


def drain_inbox(inbox_dir: Path) -> list[ACPEnvelope]:
    """Read all .msg files from *inbox_dir*, sorted by filename (ts-prefixed).

    Each file is decoded and deleted after a successful read.  Files that
    fail to decode are also deleted and their errors are silently dropped
    (malformed messages are non-recoverable; caller sees them absent).

    Returns individual envelopes without reassembly — multi-chunk
    reassembly is the session loop's responsibility.
    """
    paths = sorted(inbox_dir.glob(f"*{_MSG_SUFFIX}"))
    envelopes: list[ACPEnvelope] = []
    for path in paths:
        try:
            line = path.read_text(encoding="utf-8")
            envelopes.append(decode(line))
        except (ValueError, KeyError, OSError):
            pass
        finally:
            try:
                path.unlink()
            except OSError:
                pass
    return envelopes
