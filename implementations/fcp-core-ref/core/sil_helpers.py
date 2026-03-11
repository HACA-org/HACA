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

  check-critical-conditions Scan state/integrity.log for unresolved DRIFT_FAULT or
                            ESCALATION_FAILED records (not followed by CRITICAL_CLEARED).
                            Exits 0 if clean, 1 if unresolved condition found.

  scan-memory-drift         Run two-layer Semantic Probes against Memory Store content.
                            Layer 1: keyword/pattern checks (no inference).
                            Layer 2: gzip-NCD comparison with reference text (no LLM).
                            Exits 0 if pass, 1 if drift. Prints DRIFT_FAULT JSON on drift.

  baseline-get <key>        Print a dot-path value from state/baseline.json.
                            e.g. baseline-get thresholds.N_boot
"""

import gzip
import hashlib
import json
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
# check-critical-conditions
#
# Scans state/integrity.log for unresolved DRIFT_FAULT or ESCALATION_FAILED
# records — i.e., ones not followed by a matching CRITICAL_CLEARED record.
# Exits 0 if no unresolved critical conditions, 1 if any found.
# ---------------------------------------------------------------------------
def cmd_check_critical_conditions():
    log_path = os.path.join(root(), "state", "integrity.log")
    if not os.path.exists(log_path):
        sys.exit(0)

    critical_events = ("DRIFT_FAULT", "ESCALATION_FAILED")
    open_conditions = {}   # key → record

    with open(log_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            event = rec.get("event", "")
            if event in critical_events:
                # Use (event, detail) as key so multiple distinct faults track separately
                key = f"{event}:{rec.get('detail','')}"
                open_conditions[key] = rec
            elif event == "CRITICAL_CLEARED":
                cleared_for = rec.get("detail", "")
                # Remove any condition whose key starts with the cleared event prefix
                to_remove = [k for k in open_conditions if cleared_for and k.startswith(cleared_for)]
                for k in to_remove:
                    del open_conditions[k]

    if open_conditions:
        for key, rec in open_conditions.items():
            print(f"[SIL:CRITICAL] Unresolved: {key} at {rec.get('ts','?')}", file=sys.stderr)
        sys.exit(1)
    sys.exit(0)


# ---------------------------------------------------------------------------
# scan-memory-drift
#
# Two-layer Semantic Probe execution against Memory Store content.
# Reads state/drift-probes.jsonl and memory/session.jsonl (tail).
# Layer 1 — deterministic: keyword presence / forbidden pattern checks.
# Layer 2 — probabilistic: gzip-NCD between content excerpt and reference_text.
# No LLM invocation. Comparison is fully isolated from the CPE.
# Exits 0 if all probes pass, 1 if any probe detects drift.
# Prints a DRIFT_FAULT JSON line to stdout for each failing probe.
# ---------------------------------------------------------------------------
def _ncd_gzip(a: str, b: str) -> float:
    """Normalized Compression Distance using gzip."""
    ba = a.encode("utf-8", errors="replace")
    bb = b.encode("utf-8", errors="replace")
    bab = ba + b" " + bb
    ca = len(gzip.compress(ba, compresslevel=9))
    cb = len(gzip.compress(bb, compresslevel=9))
    cab = len(gzip.compress(bab, compresslevel=9))
    denom = max(ca, cb)
    if denom == 0:
        return 0.0
    return (cab - min(ca, cb)) / denom


def _extract_probe_data(env: dict) -> dict:
    """Extract probe fields from an ACP envelope or a raw probe object."""
    data_raw = env.get("data", env)
    if isinstance(data_raw, str):
        try:
            return json.loads(data_raw)
        except Exception:
            return {}
    return data_raw if isinstance(data_raw, dict) else {}


def _load_memory_content(scope: str) -> str:
    """Load Memory Store content according to scope spec."""
    r = root()
    session_path = os.path.join(r, "memory", "session.jsonl")
    content_parts = []

    # Parse scope: "session_tail_N" or "full_session" or "active_context"
    if scope.startswith("session_tail_"):
        try:
            tail_bytes = int(scope.split("_")[-1])
        except ValueError:
            tail_bytes = 8192
        if os.path.exists(session_path):
            with open(session_path, errors="replace") as f:
                text = f.read()
            content_parts.append(text[-tail_bytes:] if len(text) > tail_bytes else text)
    elif scope == "full_session":
        if os.path.exists(session_path):
            with open(session_path, errors="replace") as f:
                content_parts.append(f.read())
    elif scope == "active_context":
        ctx_dir = os.path.join(r, "memory", "active_context")
        if os.path.isdir(ctx_dir):
            for entry in sorted(os.listdir(ctx_dir)):
                if entry.startswith("."):
                    continue
                path = os.path.join(ctx_dir, entry)
                try:
                    with open(path, errors="replace") as f:
                        content_parts.append(f.read())
                except Exception:
                    pass
    else:
        # Default: last 8KB of session
        if os.path.exists(session_path):
            with open(session_path, errors="replace") as f:
                text = f.read()
            content_parts.append(text[-8192:] if len(text) > 8192 else text)

    return "\n".join(content_parts)


def cmd_scan_memory_drift():
    r = root()
    probes_path = os.path.join(r, "state", "drift-probes.jsonl")
    if not os.path.exists(probes_path):
        # No probes defined — pass silently
        sys.exit(0)

    # Load default tolerance from baseline
    baseline_path = os.path.join(r, "state", "baseline.json")
    default_tolerance = 0.35
    try:
        bl = json.load(open(baseline_path))
        default_tolerance = bl.get("drift", {}).get("default_tolerance", default_tolerance)
    except Exception:
        pass

    probes = []
    with open(probes_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                env = json.loads(line)
                probe = _extract_probe_data(env)
                if probe:
                    probes.append(probe)
            except Exception:
                pass

    if not probes:
        sys.exit(0)

    drift_found = False
    failures = []

    for probe in probes:
        probe_id = probe.get("id", probe.get("name", "?"))
        scope = probe.get("scope", "session_tail_8192")
        content = _load_memory_content(scope)
        tolerance = probe.get("tolerance", default_tolerance)

        # --- Layer 1: Deterministic ---
        layer = probe.get("layer", "probabilistic")
        conclusive = False
        failed = False

        if layer == "deterministic" or "expected_keywords" in probe:
            keywords = probe.get("expected_keywords", probe.get("value", ""))
            if isinstance(keywords, str):
                keywords = [keywords]
            constraint = probe.get("constraint", "required_keyword")
            for kw in keywords:
                if not isinstance(kw, str):
                    continue
                if constraint == "required_keyword":
                    if kw.lower() not in content.lower():
                        conclusive = True
                        failed = True
                        break
                elif constraint == "forbidden_pattern":
                    if kw.lower() in content.lower():
                        conclusive = True
                        failed = True
                        break
            if not failed and keywords:
                conclusive = True  # all keyword checks passed

        # --- Layer 2: Probabilistic NCD (only if Layer 1 not conclusive) ---
        if not conclusive:
            ref = probe.get("reference_text", probe.get("expected_text", ""))
            if ref and content:
                score = _ncd_gzip(content, ref)
                if score > tolerance:
                    failed = True
                    print(json.dumps({
                        "event": "DRIFT_FAULT",
                        "probe_id": probe_id,
                        "layer": "probabilistic",
                        "score": round(score, 4),
                        "tolerance": tolerance,
                    }))
            # If no reference text, cannot evaluate — pass
        elif failed:
            print(json.dumps({
                "event": "DRIFT_FAULT",
                "probe_id": probe_id,
                "layer": "deterministic",
                "constraint": probe.get("constraint", "required_keyword"),
                "value": probe.get("value", probe.get("expected_keywords", "")),
            }))

        if failed:
            drift_found = True

    sys.exit(1 if drift_found else 0)


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
    elif cmd == "check-critical-conditions":
        cmd_check_critical_conditions()
    elif cmd == "scan-memory-drift":
        cmd_scan_memory_drift()
    elif cmd == "baseline-get" and len(args) >= 2:
        cmd_baseline_get(args[1])
    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        sys.exit(1)
