#!/usr/bin/env python3
"""core/integrity.py — Integrity verification, drift detection, endure."""

import gzip
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _append_log(log_path: Path, component: str, event: str, detail: str = ""):
    entry = {"ts": _ts(), "component": component, "event": event, "detail": detail}
    with open(log_path, "a") as f:
        json.dump(entry, f)
        f.write("\n")


def _write_json_atomic(path: Path, obj: dict):
    tmp = str(path) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=2)
    os.replace(tmp, str(path))


# ---------------------------------------------------------------------------
# verify_integrity
# ---------------------------------------------------------------------------
def verify_integrity(root: Path) -> bool:
    integrity_path = root / "state" / "integrity.json"
    try:
        manifest = json.loads(integrity_path.read_text())
    except Exception as e:
        print(f"[integrity] Cannot read integrity.json: {e}", file=sys.stderr)
        return False

    failed = False
    for rel_path, expected in manifest.get("signatures", {}).items():
        p = root / rel_path
        if not p.is_file():
            print(f"[integrity] MISSING: {rel_path}", file=sys.stderr)
            failed = True
            continue
        actual = _sha256(p)
        if actual != expected:
            print(f"[integrity] MISMATCH: {rel_path}", file=sys.stderr)
            failed = True

    return not failed


# ---------------------------------------------------------------------------
# check_persona_drift
# ---------------------------------------------------------------------------
def check_persona_drift(root: Path) -> bool:
    integrity_path = root / "state" / "integrity.json"
    try:
        sigs = json.loads(integrity_path.read_text()).get("signatures", {})
    except Exception as e:
        print(f"[integrity] Cannot load integrity.json: {e}", file=sys.stderr)
        return False

    failed = False
    for rel_path, expected in sigs.items():
        if not rel_path.startswith("persona/"):
            continue
        p = root / rel_path
        if not p.is_file():
            print(f"[integrity] MISSING: {rel_path}", file=sys.stderr)
            failed = True
            continue
        if _sha256(p) != expected:
            print(f"[integrity] IDENTITY DRIFT: {rel_path}", file=sys.stderr)
            failed = True

    return not failed


# ---------------------------------------------------------------------------
# check_critical_conditions
# ---------------------------------------------------------------------------
def check_critical_conditions(root: Path) -> bool:
    """Returns True if no unresolved critical conditions."""
    log_path = root / "state" / "integrity.log"
    if not log_path.exists():
        return True

    critical_events = {"DRIFT_FAULT", "ESCALATION_FAILED"}
    open_conditions = {}

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
                key = f"{event}:{rec.get('detail', '')}"
                open_conditions[key] = rec
            elif event == "CRITICAL_CLEARED":
                cleared_for = rec.get("detail", "")
                to_remove = [k for k in open_conditions if cleared_for and k.startswith(cleared_for)]
                for k in to_remove:
                    del open_conditions[k]

    if open_conditions:
        for key, rec in open_conditions.items():
            print(f"[integrity] Unresolved: {key} at {rec.get('ts', '?')}", file=sys.stderr)
        return False
    return True


# ---------------------------------------------------------------------------
# find_unresolved_ledger
# ---------------------------------------------------------------------------
def find_unresolved_ledger(root: Path) -> list:
    session_path = root / "memory" / "session.jsonl"
    if not session_path.exists():
        return []

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

    return [{"tx": tx, "skill": d.get("skill", "unknown"), "params": d.get("params", {})}
            for tx, d in pending.items()]


# ---------------------------------------------------------------------------
# watchdog_check
# ---------------------------------------------------------------------------
def watchdog_check(component: str, root: Path) -> tuple:
    """Returns (ok: bool, message: str)."""
    log_path = root / "state" / "integrity.log"
    baseline_path = root / "state" / "baseline.json"

    threshold = 300
    try:
        bl = json.loads(baseline_path.read_text())
        threshold = bl.get("watchdog", {}).get("sil_threshold_seconds", threshold)
    except Exception:
        pass

    if not log_path.exists():
        return True, "No log yet"

    last_ts = None
    heartbeat_events = {"HEARTBEAT", "HEARTBEAT_OK"}
    with open(log_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                etype = entry.get("event") or entry.get("type", "")
                if etype in heartbeat_events:
                    last_ts = entry.get("ts", "")
            except Exception:
                pass

    if not last_ts:
        return True, "No heartbeat yet"

    try:
        last_dt = datetime.strptime(last_ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        elapsed = int((datetime.now(timezone.utc) - last_dt).total_seconds())
    except Exception:
        return True, "Cannot parse heartbeat ts"

    if elapsed <= threshold:
        return True, f"Heartbeat OK ({elapsed}s ago)"

    # SIL unresponsive
    notif_dir = root / "state" / "operator_notifications"
    notif_dir.mkdir(parents=True, exist_ok=True)
    ts_now = _ts()
    notif = {
        "type": "SIL_UNRESPONSIVE",
        "ts": ts_now,
        "component": component,
        "last_heartbeat": last_ts,
        "elapsed_seconds": elapsed,
        "threshold": threshold,
        "message": f"SIL has not written a heartbeat for {elapsed}s (threshold={threshold}s). Detected by {component}.",
    }
    notif_path = notif_dir / f"SIL_UNRESPONSIVE_{ts_now.replace(':', '')}.json"
    _write_json_atomic(notif_path, notif)
    msg = f"SIL_UNRESPONSIVE — last heartbeat {elapsed}s ago (threshold={threshold}s)"
    return False, msg


# ---------------------------------------------------------------------------
# scan_memory_drift
# ---------------------------------------------------------------------------
def _ncd_gzip(a: str, b: str) -> float:
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


def _load_memory_content(scope: str, root: Path) -> str:
    session_path = root / "memory" / "session.jsonl"
    parts = []

    if scope.startswith("session_tail_"):
        try:
            tail_bytes = int(scope.split("_")[-1])
        except ValueError:
            tail_bytes = 8192
        if session_path.exists():
            text = session_path.read_text(errors="replace")
            parts.append(text[-tail_bytes:] if len(text) > tail_bytes else text)
    elif scope == "full_session":
        if session_path.exists():
            parts.append(session_path.read_text(errors="replace"))
    elif scope == "active_context":
        ctx_dir = root / "memory" / "active_context"
        if ctx_dir.is_dir():
            for entry in sorted(ctx_dir.iterdir()):
                if entry.name.startswith("."):
                    continue
                try:
                    parts.append(entry.read_text(errors="replace"))
                except Exception:
                    pass
    else:
        if session_path.exists():
            text = session_path.read_text(errors="replace")
            parts.append(text[-8192:] if len(text) > 8192 else text)

    return "\n".join(parts)


def scan_memory_drift(root: Path) -> tuple:
    """Returns (passed: bool, detail: str)."""
    probes_path = root / "state" / "drift-probes.jsonl"
    if not probes_path.exists():
        return True, ""

    baseline_path = root / "state" / "baseline.json"
    default_tolerance = 0.35
    try:
        bl = json.loads(baseline_path.read_text())
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
                data_raw = env.get("data", env)
                if isinstance(data_raw, str):
                    try:
                        probe = json.loads(data_raw)
                    except Exception:
                        probe = {}
                else:
                    probe = data_raw if isinstance(data_raw, dict) else {}
                if probe:
                    probes.append(probe)
            except Exception:
                pass

    if not probes:
        return True, ""

    failures = []
    for probe in probes:
        probe_id = probe.get("id", probe.get("name", "?"))
        scope = probe.get("scope", "session_tail_8192")
        content = _load_memory_content(scope, root)
        tolerance = probe.get("tolerance", default_tolerance)

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
                conclusive = True

        if not conclusive:
            ref = probe.get("reference_text", probe.get("expected_text", ""))
            if ref and content:
                score = _ncd_gzip(content, ref)
                if score > tolerance:
                    failed = True
                    failures.append(json.dumps({
                        "event": "DRIFT_FAULT",
                        "probe_id": probe_id,
                        "layer": "probabilistic",
                        "score": round(score, 4),
                        "tolerance": tolerance,
                    }))
        elif failed:
            failures.append(json.dumps({
                "event": "DRIFT_FAULT",
                "probe_id": probe_id,
                "layer": "deterministic",
                "constraint": probe.get("constraint", "required_keyword"),
                "value": probe.get("value", probe.get("expected_keywords", "")),
            }))

    if failures:
        return False, "; ".join(failures)
    return True, ""


# ---------------------------------------------------------------------------
# update_integrity_hash
# ---------------------------------------------------------------------------
def update_integrity_hash(root: Path, rel_path: str):
    integrity_path = root / "state" / "integrity.json"
    manifest = json.loads(integrity_path.read_text())
    p = root / rel_path
    if p.is_file():
        manifest.setdefault("signatures", {})[rel_path] = _sha256(p)
    _write_json_atomic(integrity_path, manifest)


# ---------------------------------------------------------------------------
# endure_execute
# ---------------------------------------------------------------------------
def _read_last_chain_hash(chain_path: Path) -> str:
    if not chain_path.exists():
        return "genesis"
    last_hash = "genesis"
    with open(chain_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                last_hash = json.loads(line).get("hash", last_hash)
            except Exception:
                pass
    return last_hash


def endure_execute(root: Path) -> list:
    """Execute authorized Evolution Proposals. Returns list of log messages."""
    proposals_path = root / "state" / "pending_proposals.jsonl"
    log_path = root / "state" / "integrity.log"
    integrity_path = root / "state" / "integrity.json"
    chain_path = root / "state" / "integrity_chain.jsonl"
    session_path = root / "memory" / "session.jsonl"
    baseline_path = root / "state" / "baseline.json"

    C = 5
    try:
        bl = json.loads(baseline_path.read_text())
        C = bl.get("integrity_chain", {}).get("checkpoint_interval_C",
            bl.get("thresholds", {}).get("C_commits", C))
    except Exception:
        pass

    proposals = []
    if proposals_path.exists():
        with open(proposals_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    proposals.append(json.loads(line))
                except Exception:
                    pass

    if not proposals:
        return ["Stage 3: No pending Evolution Proposals."]

    # Load EVOLUTION_AUTH records
    auth_records = {}
    if log_path.exists():
        with open(log_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if entry.get("type") != "EVOLUTION_AUTH" and entry.get("event") != "EVOLUTION_AUTH":
                        continue
                    data_raw = entry.get("data", "{}")
                    data = json.loads(data_raw) if isinstance(data_raw, str) else data_raw
                    pid = data.get("proposal_id", "")
                    if pid:
                        auth_records[pid] = data
                except Exception:
                    pass

    manifest = json.loads(integrity_path.read_text())
    tracked = set(manifest.get("signatures", {}).keys())

    # Count existing ENDURE_COMMIT
    endure_commit_count = 0
    if log_path.exists():
        with open(log_path) as f:
            for line in f:
                try:
                    e = json.loads(line.strip())
                    if e.get("type") == "ENDURE_COMMIT" or e.get("event") == "ENDURE_COMMIT":
                        endure_commit_count += 1
                except Exception:
                    pass

    ts_now = _ts()
    messages = []
    processed = []

    for proposal in proposals:
        pid = proposal.get("proposal_id", "")
        tgt = proposal.get("target_file", "")
        content = proposal.get("content", "")
        digest = proposal.get("content_digest", "")

        auth = auth_records.get(pid)
        if not auth or auth.get("content_digest") != digest:
            msg = f"Stage 3: REJECTED {pid}: no matching EVOLUTION_AUTH."
            messages.append(msg)
            _append_log(log_path, "sil", "ENDURE_PROPOSAL_REJECTED",
                        json.dumps({"proposal_id": pid, "reason": "no_auth"}))
            processed.append(pid)
            continue

        if tgt not in tracked:
            msg = f"Stage 3: REJECTED {pid}: {tgt!r} not in tracked files."
            messages.append(msg)
            _append_log(log_path, "sil", "ENDURE_PROPOSAL_REJECTED",
                        json.dumps({"proposal_id": pid, "reason": "untracked_file", "file": tgt}))
            processed.append(pid)
            continue

        abs_tgt = root / tgt
        snap_dir = root / "memory" / "spool"
        snap_dir.mkdir(parents=True, exist_ok=True)
        snap_path = snap_dir / f"endure_snap_{pid}_{ts_now.replace(':', '')}.bak"
        if abs_tgt.exists():
            shutil.copy2(abs_tgt, snap_path)

        abs_tgt.parent.mkdir(parents=True, exist_ok=True)
        tmp = str(abs_tgt) + ".endure.tmp"
        with open(tmp, "w") as f:
            f.write(content)
        os.replace(tmp, str(abs_tgt))

        new_hash = _sha256(abs_tgt)
        manifest["signatures"][tgt] = new_hash
        _write_json_atomic(integrity_path, manifest)

        endure_commit_count += 1

        commit_data = json.dumps({
            "proposal_id": pid,
            "target_file": tgt,
            "content_digest": digest,
            "new_hash": new_hash,
            "commit_n": endure_commit_count,
        })
        _append_acp_session(session_path, "sil", "ENDURE_COMMIT", commit_data)
        _append_log(log_path, "sil", "ENDURE_COMMIT",
                    json.dumps({"proposal_id": pid, "file": tgt, "hash": new_hash}))

        if endure_commit_count % C == 0:
            prev_hash = _read_last_chain_hash(chain_path)
            chain_entry = {
                "n": endure_commit_count,
                "ts": ts_now,
                "prev": prev_hash,
                "hash": hashlib.sha256(
                    f"{prev_hash}:{tgt}:{new_hash}:{endure_commit_count}".encode()
                ).hexdigest(),
            }
            with open(chain_path, "a") as f:
                json.dump(chain_entry, f)
                f.write("\n")
            messages.append(f"Stage 3: Checkpoint appended at commit {endure_commit_count}.")

        messages.append(f"Stage 3: COMMITTED {pid} → {tgt}")
        processed.append(pid)

    remaining = [p for p in proposals if p.get("proposal_id") not in set(processed)]
    tmp = str(proposals_path) + ".tmp"
    with open(tmp, "w") as f:
        for p in remaining:
            json.dump(p, f)
            f.write("\n")
    os.replace(tmp, str(proposals_path))

    messages.append(f"Stage 3: Endure complete. {len(processed)} proposals processed.")
    return messages


def _append_acp_session(path: Path, actor: str, typ: str, data: str):
    ts = _ts()
    entry = {"actor": actor, "type": typ, "ts": ts, "data": data}
    with open(path, "a") as f:
        json.dump(entry, f)
        f.write("\n")
