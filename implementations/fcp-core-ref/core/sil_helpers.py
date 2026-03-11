#!/usr/bin/env python3
"""
core/sil_helpers.py — SIL Python helper commands.

Usage: python3 core/sil_helpers.py <command> [args...]

Commands:
  verify-integrity          Verify SHA-256 signatures in state/integrity.json.
                            Exits 0 on pass, 1 on failure.

  verify-operator-bound     Check that memory/preferences/operator.json is valid.
                            Exits 0 on pass, 1 on failure.

  check-persona-drift       Compare persona/ hashes against integrity.json.
                            Exits 0 on pass, 1 on drift.

  find-unresolved-ledger    Print unresolved ACTION_PENDING entries from session.jsonl
                            as JSON lines. Exits 0.

  baseline-get <key>        Print a dot-path value from state/baseline.json.
                            e.g. baseline-get thresholds.N_boot
"""

import json
import hashlib
import os
import sys


def root() -> str:
    r = os.environ.get("FCP_REF_ROOT", "")
    if not r:
        print("[sil_helpers] FCP_REF_ROOT not set", file=sys.stderr)
        sys.exit(1)
    return r


def load_integrity():
    p = os.path.join(root(), "state", "integrity.json")
    with open(p) as f:
        return json.load(f)


def sha256_file(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


# ---------------------------------------------------------------------------
# verify-integrity
# ---------------------------------------------------------------------------
def cmd_verify_integrity():
    r = root()
    try:
        manifest = load_integrity()
    except Exception as e:
        print(f"[SIL:PHASE2] Cannot read integrity.json: {e}", file=sys.stderr)
        sys.exit(1)

    failed = False
    for rel_path, expected in manifest.get("signatures", {}).items():
        p = os.path.join(r, rel_path)
        if not os.path.isfile(p):
            print(f"[SIL:PHASE2] MISSING: {rel_path}", file=sys.stderr)
            failed = True
            continue
        actual = sha256_file(p)
        if actual != expected:
            print(f"[SIL:PHASE2] MISMATCH: {rel_path}", file=sys.stderr)
            print(f"  expected: {expected}", file=sys.stderr)
            print(f"  actual:   {actual}", file=sys.stderr)
            failed = True

    sys.exit(1 if failed else 0)


# ---------------------------------------------------------------------------
# verify-operator-bound
# ---------------------------------------------------------------------------
def cmd_verify_operator_bound():
    p = os.path.join(root(), "memory", "preferences", "operator.json")
    if not os.path.isfile(p):
        print("[SIL:PHASE5] Operator bound file missing.", file=sys.stderr)
        sys.exit(1)
    try:
        d = json.load(open(p))
        if d.get("handle") or d.get("name"):
            sys.exit(0)
        print("[SIL:PHASE5] Operator bound malformed (no handle/name).", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"[SIL:PHASE5] Cannot parse operator.json: {e}", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# check-persona-drift
# ---------------------------------------------------------------------------
def cmd_check_persona_drift():
    r = root()
    try:
        sigs = load_integrity().get("signatures", {})
    except Exception as e:
        print(f"[SIL:VITAL] Cannot load integrity.json: {e}", file=sys.stderr)
        sys.exit(1)

    failed = False
    for rel_path, expected in sigs.items():
        if not rel_path.startswith("persona/"):
            continue
        p = os.path.join(r, rel_path)
        if not os.path.isfile(p):
            print(f"[SIL:VITAL] MISSING: {rel_path}", file=sys.stderr)
            failed = True
            continue
        if sha256_file(p) != expected:
            print(f"[SIL:VITAL] IDENTITY DRIFT: {rel_path}", file=sys.stderr)
            failed = True

    sys.exit(1 if failed else 0)


# ---------------------------------------------------------------------------
# find-unresolved-ledger
# ---------------------------------------------------------------------------
def cmd_find_unresolved_ledger():
    session_path = os.path.join(root(), "memory", "session.jsonl")
    if not os.path.exists(session_path):
        sys.exit(0)

    pending = {}
    with open(session_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                env = json.loads(line)
                data_raw = env.get("data", "{}")
                data = json.loads(data_raw) if isinstance(data_raw, str) else data_raw
                tx = env.get("tx") or data.get("tx")
                etype = env.get("type", "")
                if etype == "ACTION_PENDING" and tx:
                    pending[tx] = data
                elif etype == "ACTION_RESOLVED" and tx:
                    pending.pop(tx, None)
            except Exception:
                pass

    for tx, entry in pending.items():
        print(json.dumps({
            "tx": tx,
            "skill": entry.get("skill", "unknown"),
            "params": entry.get("params", {}),
        }))


# ---------------------------------------------------------------------------
# baseline-get <dot.path>
# ---------------------------------------------------------------------------
def cmd_baseline_get(key: str):
    p = os.path.join(root(), "state", "baseline.json")
    try:
        d = json.load(open(p))
    except Exception as e:
        print(f"[sil_helpers] Cannot read baseline.json: {e}", file=sys.stderr)
        sys.exit(1)

    parts = key.split(".")
    val = d
    for part in parts:
        if not isinstance(val, dict) or part not in val:
            print(f"[sil_helpers] Key not found: {key}", file=sys.stderr)
            sys.exit(1)
        val = val[part]

    print(val)


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)

    cmd = args[0]
    if cmd == "verify-integrity":
        cmd_verify_integrity()
    elif cmd == "verify-operator-bound":
        cmd_verify_operator_bound()
    elif cmd == "check-persona-drift":
        cmd_check_persona_drift()
    elif cmd == "find-unresolved-ledger":
        cmd_find_unresolved_ledger()
    elif cmd == "baseline-get" and len(args) >= 2:
        cmd_baseline_get(args[1])
    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        sys.exit(1)
