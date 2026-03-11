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

  endure-execute            Execute queued Operator-authorized Evolution Proposals
                            (Sleep Cycle Stage 3). Verifies EVOLUTION_AUTH, applies
                            atomic writes, updates integrity.json, emits ENDURE_COMMIT.
                            Exits 0 on success.

  watchdog-check <component> Check SIL heartbeat freshness from state/integrity.log.
                            If SIL has been silent beyond watchdog.sil_threshold_seconds,
                            writes SIL_UNRESPONSIVE notification to Operator Channel and
                            exits 1. Exits 0 if heartbeat is current.
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
# endure-execute
#
# Executes queued, Operator-authorized Evolution Proposals (Sleep Cycle Stage 3).
# For each proposal in state/pending_proposals.jsonl:
#   1. Verify matching EVOLUTION_AUTH record exists in state/integrity.log
#      (proposal_id AND content_digest must match).
#   2. Verify target_file is tracked in state/integrity.json (structural file).
#   3. Write new content atomically (write-to-temp + os.replace).
#   4. Recompute SHA-256 hash; update state/integrity.json atomically.
#   5. Append ENDURE_COMMIT envelope to memory/session.jsonl.
#   6. Append checkpoint to state/integrity_chain.jsonl if C commits accumulated.
# Proposals without a valid EVOLUTION_AUTH are discarded and logged.
# Clears state/pending_proposals.jsonl after processing.
# Exits 0 on success (even if some proposals were rejected).
# ---------------------------------------------------------------------------
def cmd_endure_execute():
    import tempfile
    from datetime import datetime, timezone

    r = root()
    proposals_path   = os.path.join(r, "state", "pending_proposals.jsonl")
    log_path         = os.path.join(r, "state", "integrity.log")
    integrity_path   = os.path.join(r, "state", "integrity.json")
    chain_path       = os.path.join(r, "state", "integrity_chain.jsonl")
    session_path     = os.path.join(r, "memory", "session.jsonl")
    baseline_path    = os.path.join(r, "state", "baseline.json")

    # Load C (checkpoint interval) from baseline
    C = 5
    try:
        bl = json.load(open(baseline_path))
        C = bl.get("integrity", {}).get("C_commits", C)
    except Exception:
        pass

    # Load pending proposals
    proposals = []
    try:
        with open(proposals_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    proposals.append(json.loads(line))
                except Exception:
                    pass
    except Exception:
        pass

    if not proposals:
        print("Stage 3: No pending Evolution Proposals.", file=sys.stderr)
        return

    # Load EVOLUTION_AUTH records from integrity.log
    auth_records = {}  # proposal_id → {content_digest, operator, ts}
    try:
        with open(log_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if entry.get("type") != "EVOLUTION_AUTH":
                        continue
                    data_raw = entry.get("data", "{}")
                    data = json.loads(data_raw) if isinstance(data_raw, str) else data_raw
                    pid = data.get("proposal_id", "")
                    if pid:
                        auth_records[pid] = data
                except Exception:
                    pass
    except Exception:
        pass

    # Load current integrity manifest
    try:
        manifest = json.load(open(integrity_path))
    except Exception as e:
        print(f"Stage 3: Cannot read integrity.json: {e}", file=sys.stderr)
        return

    tracked = set(manifest.get("signatures", {}).keys())

    # Count existing Endure commits for checkpoint logic
    endure_commit_count = 0
    try:
        with open(log_path) as f:
            for line in f:
                try:
                    if json.loads(line.strip()).get("type") == "ENDURE_COMMIT":
                        endure_commit_count += 1
                except Exception:
                    pass
    except Exception:
        pass

    ts_now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    processed = []

    for proposal in proposals:
        pid     = proposal.get("proposal_id", "")
        tgt     = proposal.get("target_file", "")
        content = proposal.get("content", "")
        digest  = proposal.get("content_digest", "")

        # --- Gate 1: EVOLUTION_AUTH must exist with matching digest ---
        auth = auth_records.get(pid)
        if not auth or auth.get("content_digest") != digest:
            print(f"Stage 3: REJECTED {pid}: no matching EVOLUTION_AUTH.", file=sys.stderr)
            _append_log(log_path, "sil", "ENDURE_PROPOSAL_REJECTED",
                        json.dumps({"proposal_id": pid, "reason": "no_auth"}))
            processed.append(pid)
            continue

        # --- Gate 2: target_file must be tracked in integrity.json ---
        if tgt not in tracked:
            print(f"Stage 3: REJECTED {pid}: {tgt!r} not in tracked files.", file=sys.stderr)
            _append_log(log_path, "sil", "ENDURE_PROPOSAL_REJECTED",
                        json.dumps({"proposal_id": pid, "reason": "untracked_file", "file": tgt}))
            processed.append(pid)
            continue

        abs_tgt = os.path.join(r, tgt)

        # --- Snapshot ---
        snap_dir = os.path.join(r, "memory", "spool")
        os.makedirs(snap_dir, exist_ok=True)
        snap_path = os.path.join(snap_dir, f"endure_snap_{pid}_{ts_now.replace(':', '')}.bak")
        if os.path.exists(abs_tgt):
            import shutil
            shutil.copy2(abs_tgt, snap_path)

        # --- Atomic write ---
        os.makedirs(os.path.dirname(abs_tgt), exist_ok=True)
        tmp = abs_tgt + ".endure.tmp"
        with open(tmp, "w") as f:
            f.write(content)
        os.replace(tmp, abs_tgt)

        # --- Update integrity.json hash atomically ---
        new_hash = sha256_file(abs_tgt)
        manifest["signatures"][tgt] = new_hash
        _write_json_atomic(integrity_path, manifest)

        # --- Increment commit counter ---
        endure_commit_count += 1

        # --- Emit ENDURE_COMMIT to session.jsonl ---
        commit_data = json.dumps({
            "proposal_id":   pid,
            "target_file":   tgt,
            "content_digest": digest,
            "new_hash":      new_hash,
            "commit_n":      endure_commit_count,
        })
        _append_acp(session_path, "sil", "ENDURE_COMMIT", commit_data)
        _append_log(log_path, "sil", "ENDURE_COMMIT",
                    json.dumps({"proposal_id": pid, "file": tgt, "hash": new_hash}))

        # --- Integrity chain checkpoint (every C commits) ---
        if endure_commit_count % C == 0:
            prev_hash = _read_last_chain_hash(chain_path)
            chain_entry = {
                "n":    endure_commit_count,
                "ts":   ts_now,
                "prev": prev_hash,
                "hash": hashlib.sha256(
                    f"{prev_hash}:{tgt}:{new_hash}:{endure_commit_count}".encode()
                ).hexdigest(),
            }
            with open(chain_path, "a") as f:
                json.dump(chain_entry, f)
                f.write("\n")
            print(f"Stage 3: Checkpoint appended at commit {endure_commit_count}.", file=sys.stderr)

        print(f"Stage 3: COMMITTED {pid} → {tgt}", file=sys.stderr)
        processed.append(pid)

    # Clear processed proposals from pending_proposals.jsonl
    remaining = [p for p in proposals if p.get("proposal_id") not in set(processed)]
    tmp = proposals_path + ".tmp"
    with open(tmp, "w") as f:
        for p in remaining:
            json.dump(p, f)
            f.write("\n")
    os.replace(tmp, proposals_path)

    print(f"Stage 3: Endure complete. {len(processed)} proposals processed.", file=sys.stderr)


# ---------------------------------------------------------------------------
# watchdog-check <component>
#
# Reads the most recent HEARTBEAT or HEARTBEAT_OK record from state/integrity.log.
# Computes elapsed seconds since that record's timestamp.
# If elapsed > watchdog.sil_threshold_seconds (from baseline.json):
#   - Writes SIL_UNRESPONSIVE notification to state/operator_notifications/
#   - Exits 1 (caller should escalate / halt operation)
# Exits 0 if heartbeat is current or log is absent (boot time).
# ---------------------------------------------------------------------------
def cmd_watchdog_check(component: str):
    import time
    from datetime import datetime, timezone

    r = root()
    log_path      = os.path.join(r, "state", "integrity.log")
    baseline_path = os.path.join(r, "state", "baseline.json")
    notif_dir     = os.path.join(r, "state", "operator_notifications")

    # Load threshold
    threshold = 300
    try:
        bl = json.load(open(baseline_path))
        threshold = bl.get("watchdog", {}).get("sil_threshold_seconds", threshold)
    except Exception:
        pass

    # Find the most recent HEARTBEAT/HEARTBEAT_OK timestamp.
    # integrity.log uses {"ts":..., "component":..., "event":..., "detail":...}
    # ACP-format entries from other writers use {"type":..., "ts":...}
    last_heartbeat_ts = None
    heartbeat_events = {"HEARTBEAT", "HEARTBEAT_OK"}
    try:
        with open(log_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    # Support both integrity_log format (event) and ACP format (type)
                    etype = entry.get("event") or entry.get("type", "")
                    if etype in heartbeat_events:
                        last_heartbeat_ts = entry.get("ts", "")
                except Exception:
                    pass
    except FileNotFoundError:
        sys.exit(0)  # Log absent → boot time, no issue
    except Exception:
        sys.exit(0)

    if not last_heartbeat_ts:
        sys.exit(0)  # No heartbeat yet → first session, OK

    # Parse and compare
    try:
        fmt = "%Y-%m-%dT%H:%M:%SZ"
        last_dt = datetime.strptime(last_heartbeat_ts, fmt).replace(tzinfo=timezone.utc)
        now_dt  = datetime.now(timezone.utc)
        elapsed = int((now_dt - last_dt).total_seconds())
    except Exception:
        sys.exit(0)

    if elapsed <= threshold:
        sys.exit(0)

    # SIL is unresponsive — write notification bypassing SIL
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    notification = {
        "type":             "SIL_UNRESPONSIVE",
        "ts":               ts,
        "component":        component,
        "last_heartbeat":   last_heartbeat_ts,
        "elapsed_seconds":  elapsed,
        "threshold":        threshold,
        "message": (
            f"SIL has not written a heartbeat for {elapsed}s "
            f"(threshold={threshold}s). Detected by {component}."
        ),
    }
    os.makedirs(notif_dir, exist_ok=True)
    notif_path = os.path.join(notif_dir, f"SIL_UNRESPONSIVE_{ts.replace(':', '')}.json")
    _write_json_atomic(notif_path, notification)
    print(
        f"[{component.upper()}] WARNING: SIL_UNRESPONSIVE — "
        f"last heartbeat {elapsed}s ago (threshold={threshold}s). "
        f"Notification written to Operator Channel.",
        file=sys.stderr,
    )
    sys.exit(1)


def _append_log(log_path: str, actor: str, etype: str, data: str):
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    entry = {"actor": actor, "type": etype, "ts": ts, "data": data}
    with open(log_path, "a") as f:
        json.dump(entry, f)
        f.write("\n")


def _append_acp(path: str, actor: str, etype: str, data: str):
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    entry = {"actor": actor, "type": etype, "ts": ts, "data": data}
    with open(path, "a") as f:
        json.dump(entry, f)
        f.write("\n")


def _write_json_atomic(path: str, obj: dict):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=2)
    os.replace(tmp, path)


def _read_last_chain_hash(chain_path: str) -> str:
    """Return the hash field of the last entry in the chain, or 'genesis'."""
    if not os.path.exists(chain_path):
        return "genesis"
    last_hash = "genesis"
    try:
        with open(chain_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    last_hash = json.loads(line).get("hash", last_hash)
                except Exception:
                    pass
    except Exception:
        pass
    return last_hash


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
    elif cmd == "endure-execute":
        cmd_endure_execute()
    elif cmd == "watchdog-check" and len(args) >= 2:
        cmd_watchdog_check(args[1])
    elif cmd == "baseline-get" and len(args) >= 2:
        cmd_baseline_get(args[1])
    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        sys.exit(1)
