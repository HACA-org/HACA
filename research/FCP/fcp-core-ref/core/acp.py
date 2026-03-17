#!/usr/bin/env python3
"""
core/acp.py — ACP (Atomic Chunked Protocol) implementation.

Also usable as CLI for compatibility with bash skills:
  python3 -m core.acp write <actor> <type> <data> [tx] [seq] [eof]
"""

import json
import os
import sys
import time
import uuid
import zlib
from pathlib import Path


def crc32(data: str) -> str:
    return format(zlib.crc32(data.encode("utf-8")) & 0xFFFFFFFF, "08x")


def new_tx() -> str:
    return str(uuid.uuid4())


def next_gseq(actor: str, root: Path) -> int:
    sentinel_dir = root / "state" / "sentinels"
    sentinel_dir.mkdir(parents=True, exist_ok=True)
    seq_file = sentinel_dir / f"{actor}.gseq"
    lock_dir = sentinel_dir / f"{actor}.gseq.lock"

    attempts = 0
    while True:
        try:
            lock_dir.mkdir()
            break
        except FileExistsError:
            attempts += 1
            if attempts >= 20:
                break
            time.sleep(0.05)

    current = 0
    if seq_file.exists():
        try:
            current = int(seq_file.read_text().strip())
        except (ValueError, OSError):
            pass
    nxt = current + 1
    seq_file.write_text(str(nxt))

    try:
        lock_dir.rmdir()
    except OSError:
        pass

    return nxt


def _build_envelope(actor, gseq, tx, seq, eof, typ, ts, data, checksum):
    return {
        "actor": actor,
        "gseq": gseq,
        "tx": tx,
        "seq": seq,
        "eof": eof,
        "type": typ,
        "ts": ts,
        "data": data,
        "crc": checksum,
    }


def write(
    actor: str,
    typ: str,
    data: str,
    root: Path,
    tx: str = None,
    seq: int = 1,
    eof: bool = True,
) -> Path:
    from datetime import datetime, timezone

    if tx is None:
        tx = new_tx()

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    checksum = crc32(data)
    gseq = next_gseq(actor, root)

    spool_dir = root / "memory" / "spool" / actor
    inbox_dir = root / "memory" / "inbox"
    spool_dir.mkdir(parents=True, exist_ok=True)
    inbox_dir.mkdir(parents=True, exist_ok=True)

    epoch_ns = int(time.time() * 1e9)
    tmp_file = spool_dir / f"{epoch_ns}-{gseq}.tmp"
    msg_file = inbox_dir / f"{epoch_ns}-{gseq}.msg"

    envelope = _build_envelope(actor, gseq, tx, seq, eof, typ, ts, data, checksum)
    tmp_file.write_text(json.dumps(envelope, ensure_ascii=False) + "\n")

    # fsync before rename
    try:
        fd = os.open(str(tmp_file), os.O_RDONLY)
        os.fsync(fd)
        os.close(fd)
    except OSError:
        pass

    os.replace(tmp_file, msg_file)
    return msg_file


def write_presession(
    actor: str,
    typ: str,
    data: str,
    root: Path,
    tx: str = None,
    seq: int = 1,
    eof: bool = True,
) -> Path:
    from datetime import datetime, timezone

    presession_dir = root / "memory" / "inbox" / "presession"
    presession_dir.mkdir(parents=True, exist_ok=True)

    # Check capacity
    try:
        baseline_path = root / "state" / "baseline.json"
        bl = json.loads(baseline_path.read_text())
        capacity = bl.get("pre_session_buffer", {}).get("capacity", 100)
    except Exception:
        capacity = 100

    current = len(list(presession_dir.glob("*.msg")))
    if current >= capacity:
        notif_dir = root / "state" / "operator_notifications"
        notif_dir.mkdir(parents=True, exist_ok=True)
        ts_now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        notif = {
            "type": "PRE_SESSION_BUFFER_OVERFLOW",
            "ts": ts_now,
            "component": actor,
            "capacity": capacity,
            "count": current,
            "message": f"Pre-session buffer full ({current}/{capacity}). Stimulus rejected.",
        }
        notif_path = notif_dir / f"PSB_OVERFLOW_{ts_now.replace(':', '')}.json"
        tmp = str(notif_path) + ".tmp"
        with open(tmp, "w") as f:
            json.dump(notif, f, indent=2)
        os.replace(tmp, str(notif_path))
        print(f"[acp] OVERFLOW: pre-session buffer at capacity ({current}/{capacity}). Rejected.", file=sys.stderr)
        raise OverflowError("presession buffer full")

    if tx is None:
        tx = new_tx()

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    checksum = crc32(data)
    gseq = next_gseq(actor, root)

    spool_dir = root / "memory" / "spool" / actor
    spool_dir.mkdir(parents=True, exist_ok=True)

    epoch_ns = int(time.time() * 1e9)
    tmp_file = spool_dir / f"{epoch_ns}-{gseq}.tmp"
    msg_file = presession_dir / f"{epoch_ns}-{gseq}.msg"

    envelope = _build_envelope(actor, gseq, tx, seq, eof, typ, ts, data, checksum)
    tmp_file.write_text(json.dumps(envelope, ensure_ascii=False) + "\n")

    try:
        fd = os.open(str(tmp_file), os.O_RDONLY)
        os.fsync(fd)
        os.close(fd)
    except OSError:
        pass

    os.replace(tmp_file, msg_file)
    return msg_file


def read_inbox(root: Path) -> list:
    inbox_dir = root / "memory" / "inbox"
    if not inbox_dir.is_dir():
        return []
    msgs = sorted(inbox_dir.glob("*.msg"))
    result = []
    for msg in msgs:
        try:
            result.append(json.loads(msg.read_text()))
        except Exception:
            pass
    return result


def read_session(root: Path, limit: int = 50) -> list:
    session_path = root / "memory" / "session.jsonl"
    if not session_path.exists():
        return []
    lines = session_path.read_text().splitlines()
    result = []
    for line in lines[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            result.append(json.loads(line))
        except Exception:
            pass
    return list(reversed(result))


# ---------------------------------------------------------------------------
# CLI for bash skill compatibility
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 -m core.acp write <actor> <type> <data> [tx] [seq] [eof]", file=sys.stderr)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "write":
        if len(sys.argv) < 5:
            print("Usage: python3 -m core.acp write <actor> <type> <data>", file=sys.stderr)
            sys.exit(1)
        actor = sys.argv[2]
        typ = sys.argv[3]
        data = sys.argv[4]
        tx = sys.argv[5] if len(sys.argv) > 5 else None
        seq = int(sys.argv[6]) if len(sys.argv) > 6 else 1
        eof = (sys.argv[7].lower() != "false") if len(sys.argv) > 7 else True

        root_env = os.environ.get("FCP_REF_ROOT", "")
        if not root_env:
            print("[acp] FCP_REF_ROOT not set", file=sys.stderr)
            sys.exit(1)
        root = Path(root_env)
        msg_file = write(actor, typ, data, root, tx=tx, seq=seq, eof=eof)
        print(msg_file)

    elif cmd == "new_tx":
        print(new_tx())

    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        sys.exit(1)
