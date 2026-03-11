"""ACP (Atomic Chunked Protocol) envelope — FCP-Core §3.1.

The ACP envelope is the universal inter-component message format.  It is used:
  - As .msg files in io/inbox/ for async delivery between components
  - As lines in memory/session.jsonl (session store)
  - As lines in state/integrity.log (integrity record)

Wire format (JSON object):
  {
    "actor": "sil",            # component that produced this envelope
    "gseq":  1042,             # monotonically increasing counter, per actor per session
    "tx":    "<uuid>",         # transaction UUID; ties multi-chunk envelopes
    "seq":   1,                # position within the transaction (1-indexed)
    "eof":   true,             # true if last envelope in the transaction
    "type":  "HEARTBEAT",      # envelope type
    "ts":    "2026-03-11T...", # ISO 8601 UTC
    "data":  "...",            # UTF-8 payload; structured payloads JSON-serialised
    "crc":   "a1b2c3d4"        # CRC-32 of data, 8-char lowercase hex
  }

Size limit: 4000 bytes per envelope.  Larger payloads are chunked.
"""

from __future__ import annotations

import binascii
import dataclasses
import json
import uuid
from typing import Any

from .fs import utcnow_iso

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_ENVELOPE_BYTES = 4000  # §3.1: no single ACP envelope may exceed 4000 bytes

# ---------------------------------------------------------------------------
# Actor identifiers (§3.1)
# ---------------------------------------------------------------------------

ACTOR_FCP  = "fcp"
ACTOR_SIL  = "sil"
ACTOR_MIL  = "mil"
ACTOR_CPE  = "cpe"
ACTOR_EXEC = "exec"

# ---------------------------------------------------------------------------
# Envelope types (§3.1 table)
# ---------------------------------------------------------------------------

TYPE_MSG                = "MSG"
TYPE_SKILL_REQUEST      = "SKILL_REQUEST"
TYPE_SKILL_RESULT       = "SKILL_RESULT"
TYPE_SKILL_ERROR        = "SKILL_ERROR"
TYPE_SKILL_TIMEOUT      = "SKILL_TIMEOUT"
TYPE_HEARTBEAT          = "HEARTBEAT"
TYPE_DRIFT_FAULT        = "DRIFT_FAULT"
TYPE_EVOLUTION_PROPOSAL = "EVOLUTION_PROPOSAL"
TYPE_EVOLUTION_AUTH     = "EVOLUTION_AUTH"
TYPE_EVOLUTION_REJECTED = "EVOLUTION_REJECTED"
TYPE_PROPOSAL_PENDING   = "PROPOSAL_PENDING"
TYPE_ENDURE_COMMIT      = "ENDURE_COMMIT"
TYPE_SLEEP_COMPLETE     = "SLEEP_COMPLETE"
TYPE_ACTION_LEDGER      = "ACTION_LEDGER"
TYPE_SIL_UNRESPONSIVE   = "SIL_UNRESPONSIVE"
TYPE_CTX_SKIP           = "CTX_SKIP"
TYPE_STRUCTURAL_ANOMALY = "STRUCTURAL_ANOMALY"
TYPE_CRITICAL_CLEARED   = "CRITICAL_CLEARED"
TYPE_CRON_WAKE          = "CRON_WAKE"
TYPE_DECOMMISSION       = "DECOMMISSION"
TYPE_SESSION_CLOSE      = "SESSION_CLOSE"
TYPE_CRASH_RECOVERY     = "CRASH_RECOVERY"


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class ACPEnvelope:
    actor: str
    gseq:  int
    tx:    str
    seq:   int
    eof:   bool
    type:  str
    ts:    str
    data:  str
    crc:   str

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "ACPEnvelope":
        return ACPEnvelope(
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


# ---------------------------------------------------------------------------
# CRC helper
# ---------------------------------------------------------------------------

def _crc32(data: str) -> str:
    """Return 8-character lowercase hex CRC-32 of *data* (UTF-8 encoded)."""
    val = binascii.crc32(data.encode("utf-8")) & 0xFFFFFFFF
    return f"{val:08x}"


# ---------------------------------------------------------------------------
# Envelope builder
# ---------------------------------------------------------------------------

def build_envelope(
    actor:   str,
    type_:   str,
    data:    str,
    gseq:    int,
    tx:      str | None = None,
    seq:     int = 1,
    eof:     bool = True,
    ts:      str | None = None,
) -> ACPEnvelope:
    """Build a single ACP envelope.

    Args:
        actor:  Component identity (ACTOR_* constant).
        type_:  Envelope type (TYPE_* constant).
        data:   UTF-8 payload string.  Structured payloads should be
                JSON-serialised by the caller before passing here.
        gseq:   Per-actor monotonic sequence counter for this session.
        tx:     Transaction UUID.  Auto-generated if None.
        seq:    Position within transaction (1-indexed, default 1).
        eof:    True if this is the last envelope in the transaction.
        ts:     ISO 8601 UTC timestamp.  Current time used if None.

    Returns:
        ACPEnvelope instance.

    Raises:
        ValueError: if the encoded envelope exceeds MAX_ENVELOPE_BYTES.
    """
    if tx is None:
        tx = str(uuid.uuid4())
    if ts is None:
        ts = utcnow_iso()

    envelope = ACPEnvelope(
        actor=actor,
        gseq=gseq,
        tx=tx,
        seq=seq,
        eof=eof,
        type=type_,
        ts=ts,
        data=data,
        crc=_crc32(data),
    )

    encoded = envelope.to_json()
    if len(encoded.encode("utf-8")) > MAX_ENVELOPE_BYTES:
        raise ValueError(
            f"ACP envelope exceeds {MAX_ENVELOPE_BYTES} bytes "
            f"({len(encoded.encode('utf-8'))} bytes).  Use chunk_payload() "
            "for large payloads."
        )

    return envelope


# ---------------------------------------------------------------------------
# Chunker — for payloads > 4000 bytes
# ---------------------------------------------------------------------------

def chunk_payload(
    actor:       str,
    type_:       str,
    payload_str: str,
    gseq_start:  int,
) -> list[ACPEnvelope]:
    """Split *payload_str* across multiple ACP envelopes, each ≤ 4000 bytes.

    The envelopes share a common transaction UUID and carry incrementing
    ``seq`` values with ``eof=True`` on the final chunk.

    Args:
        actor:       Component identity.
        type_:       Envelope type applied to every chunk.
        payload_str: Raw payload string to chunk.
        gseq_start:  Starting gseq value.  Each chunk increments by 1.

    Returns:
        List of ACPEnvelope instances in sequence order.
    """
    tx = str(uuid.uuid4())
    ts = utcnow_iso()

    # Determine safe chunk size by binary-search approximation.
    # Overhead budget: reserve 200 bytes for envelope metadata fields.
    OVERHEAD = 200
    max_data_bytes = MAX_ENVELOPE_BYTES - OVERHEAD

    # Split payload_str into UTF-8 byte chunks.
    payload_bytes = payload_str.encode("utf-8")
    chunks: list[str] = []
    pos = 0
    while pos < len(payload_bytes):
        chunk_bytes = payload_bytes[pos : pos + max_data_bytes]
        chunks.append(chunk_bytes.decode("utf-8", errors="replace"))
        pos += max_data_bytes

    envelopes: list[ACPEnvelope] = []
    for idx, chunk_data in enumerate(chunks, start=1):
        is_last = idx == len(chunks)
        gseq = gseq_start + (idx - 1)
        env = ACPEnvelope(
            actor=actor,
            gseq=gseq,
            tx=tx,
            seq=idx,
            eof=is_last,
            type=type_,
            ts=ts,
            data=chunk_data,
            crc=_crc32(chunk_data),
        )
        envelopes.append(env)

    return envelopes


# ---------------------------------------------------------------------------
# Sequence counter helper
# ---------------------------------------------------------------------------

class GseqCounter:
    """Thread-unsafe monotonic gseq counter per actor.

    FCP-Core §3.1 requires a per-actor monotonic counter that resets per
    session.  Instantiate one GseqCounter per actor at session start.
    """

    def __init__(self, actor: str) -> None:
        self.actor = actor
        self._value = 0

    def next(self) -> int:
        self._value += 1
        return self._value

    @property
    def value(self) -> int:
        return self._value


# ---------------------------------------------------------------------------
# Envelope validator
# ---------------------------------------------------------------------------

def validate_envelope(d: dict[str, Any]) -> list[str]:
    """Return a list of validation errors for the envelope dict *d*.

    An empty list means the envelope is well-formed.
    """
    errors: list[str] = []
    required = {"actor", "gseq", "tx", "seq", "eof", "type", "ts", "data", "crc"}
    missing = required - set(d.keys())
    if missing:
        errors.append(f"missing fields: {missing}")
        return errors  # nothing more to check

    # CRC verification
    expected = _crc32(str(d["data"]))
    if d["crc"] != expected:
        errors.append(f"crc mismatch: expected {expected}, got {d['crc']}")

    # Type check
    if not isinstance(d["gseq"], int) or d["gseq"] < 1:
        errors.append(f"gseq must be a positive integer, got {d['gseq']!r}")
    if not isinstance(d["seq"], int) or d["seq"] < 1:
        errors.append(f"seq must be a positive integer, got {d['seq']!r}")
    if not isinstance(d["eof"], bool):
        errors.append(f"eof must be boolean, got {d['eof']!r}")

    return errors
