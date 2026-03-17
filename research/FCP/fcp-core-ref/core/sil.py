#!/usr/bin/env python3
"""
core/sil.py — System Integrity Layer. Main entry point for a cognitive session.

Usage:
  python3 core/sil.py [--dry-run] [--skip-drift]
  python3 core/sil.py endure list
  python3 core/sil.py endure approve <proposal_id>
"""

import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_json_atomic(path: Path, obj: dict):
    tmp = str(path) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=2)
    os.replace(tmp, str(path))


# Ensure package is importable when run as a script
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))


class SIL:
    def __init__(self, root: Path, dry_run: bool = False, skip_drift: bool = False):
        self.root = root
        self.dry_run = dry_run
        self.skip_drift = skip_drift

        # Paths
        self.token_file = root / "state" / "sentinels" / "session.token"
        self.recovery_file = root / "state" / "sentinels" / "recovery.attempts"
        self.beacon_file = root / "state" / "distress.beacon"
        self.integrity_log = root / "state" / "integrity.log"
        self.semantic_digest = root / "state" / "semantic-digest.json"

        # Runtime state
        self.cycle_count = 0
        self.last_vital_check = time.time()
        self.cpe_empty_count = 0
        self.context_critical = False

        # Loaded after phase1
        self.config = None
        self.mil = None
        self.exec_layer = None
        self.cpe = None
        self.acp_root = root  # used before config loaded

    # -------------------------------------------------------------------------
    # Logging helpers
    # -------------------------------------------------------------------------
    def sil_log(self, category: str, message: str):
        print(f"[SIL:{category}] {message}", file=sys.stderr)

    def integrity_log_write(self, event: str, detail: str = "", component: str = "sil"):
        entry = {"ts": _ts(), "component": component, "event": event, "detail": detail}
        with open(self.integrity_log, "a") as f:
            json.dump(entry, f)
            f.write("\n")

    def operator_notify(self, severity: str, component: str, message: str) -> bool:
        channel_dir = self.root / self.config.operator_channel_path
        channel_dir.mkdir(parents=True, exist_ok=True)
        ts = _ts()
        fname = f"{ts.replace(':', '').replace('-', '')}_{severity}_{component}.json"
        notif_path = channel_dir / fname
        payload = {"ts": ts, "severity": severity, "component": component, "message": message}
        try:
            tmp = str(notif_path) + ".tmp"
            with open(tmp, "w") as f:
                json.dump(payload, f)
            os.replace(tmp, str(notif_path))
            self.integrity_log_write("OPERATOR_CHANNEL_SENT", f"severity={severity}")
            self.sil_log("CHANNEL", f"[{severity}] {component}: {message}")
            return True
        except Exception as e:
            self.integrity_log_write("OPERATOR_CHANNEL_FAIL", f"severity={severity}")
            self.sil_log("CHANNEL", f"Failed to write notification: {e}")
            return False

    def operator_notify_with_retry(self, severity: str, component: str, message: str):
        for attempt in range(self.config.N_channel):
            if self.operator_notify(severity, component, message):
                return
            self.sil_log("CHANNEL", f"Attempt {attempt + 1}/{self.config.N_channel} failed.")
        self.sil_log("FATAL", f"Operator Channel exhausted after {self.config.N_channel} attempts.")
        self._distress_beacon_activate("operator_channel_failure")
        sys.exit(1)

    def _distress_beacon_activate(self, reason: str):
        payload = {"active": True, "activated_at": _ts(), "reason": reason}
        _write_json_atomic(self.beacon_file, payload)
        self.integrity_log_write("DISTRESS_BEACON_ACTIVATED", reason)
        self.sil_log("BEACON", f"Distress Beacon activated: {reason}")

    # -------------------------------------------------------------------------
    # Boot phases
    # -------------------------------------------------------------------------
    def _prereq_beacon(self):
        if self.beacon_file.exists():
            self.sil_log("HALT", "Passive Distress Beacon is active. Resolve the condition first.")
            self.sil_log("HALT", f"Then: rm {self.beacon_file}")
            sys.exit(1)

    def _phase0_sandbox(self):
        # Check topology (requires baseline loaded first, but we do a raw read here)
        baseline_path = self.root / "state" / "baseline.json"
        try:
            topology = json.loads(baseline_path.read_text()).get("topology", "")
        except Exception:
            topology = ""
        if topology != "transparent":
            self.sil_log("FATAL", f"Axiom I: Declared topology '{topology}' is not 'transparent'. Boot aborted.")
            sys.exit(1)

        # Confinement check
        cgroup = Path("/proc/1/cgroup")
        try:
            cg_content = cgroup.read_text()
            if os.getpid() == 1 or any(x in cg_content for x in ("docker", "lxc", "containerd", "libpod")):
                self.sil_log("BOOT", "Confinement verified (container environment).")
                return
        except Exception:
            pass

        # Try unshare re-execution
        import shutil
        if shutil.which("unshare"):
            self.sil_log("BOOT", "Re-executing inside private namespace...")
            os.execvp("unshare", [
                "unshare", "-m", "-p", "-f", "-r", "--mount-proc",
                sys.executable, __file__
            ] + sys.argv[1:])
            # execvp does not return

        # Fallback: write boundary test
        test_path = f"/tmp/fcp_boundary_test_{os.getpid()}"
        try:
            Path(test_path).touch()
            os.unlink(test_path)
            self.sil_log("WARN", "Namespace isolation unavailable; boundary test passed.")
        except Exception:
            self.sil_log("FATAL", "Axiom I: Confinement Fault — unshare unavailable and boundary test failed.")
            sys.exit(1)

    def _phase1_baseline(self):
        from core.config import Config
        self.config = Config(self.root)
        (self.root / self.config.operator_channel_path).mkdir(parents=True, exist_ok=True)
        self.token_file.parent.mkdir(parents=True, exist_ok=True)
        self.sil_log("BOOT", "Structural baseline loaded.")

    def _phase2_integrity(self):
        from core.integrity import verify_integrity
        self.sil_log("BOOT", "Verifying Integrity Document...")
        if not verify_integrity(self.root):
            self.integrity_log_write("INTEGRITY_MISMATCH", "boot")
            self.sil_log("FATAL", "Integrity mismatch — Axiom II Violation. Boot aborted.")
            sys.exit(1)
        self.integrity_log_write("INTEGRITY_OK", "boot")

    def _phase3_crash_recovery(self):
        crash_count = 0
        if self.recovery_file.exists():
            try:
                crash_count = int(self.recovery_file.read_text().strip())
            except (ValueError, OSError):
                pass

        if not self.token_file.exists():
            self.recovery_file.write_text("0")
            return

        self.sil_log("RECOVERY", "Stale session token — crash or incomplete Sleep Cycle detected.")
        self.integrity_log_write("CRASH_DETECTED", "stale_token")
        crash_count += 1
        self.recovery_file.write_text(str(crash_count))

        if crash_count >= self.config.N_boot:
            self.sil_log("FATAL", f"Boot loop: {crash_count} crashes (N_boot={self.config.N_boot}).")
            self._distress_beacon_activate(f"boot_loop_{crash_count}")
            self.operator_notify_with_retry("CRITICAL", "sil",
                f"Boot loop: {crash_count} consecutive crashes. Beacon activated.")
            sys.exit(1)

        self.operator_notify("WARN", "sil", f"Crash recovery boot {crash_count} of {self.config.N_boot}.")
        self._review_action_ledger()
        self.token_file.unlink(missing_ok=True)
        self.sil_log("RECOVERY", "Stale token cleared.")

    def _review_action_ledger(self):
        from core.integrity import find_unresolved_ledger
        unresolved = find_unresolved_ledger(self.root)
        if not unresolved:
            self.sil_log("RECOVERY", "Action Ledger: no unresolved entries.")
            return

        self.sil_log("RECOVERY", "Unresolved Action Ledger entries — Operator review required.")
        self.integrity_log_write("ACTION_LEDGER_UNRESOLVED", "see_operator_notifications")
        self.operator_notify("CRITICAL", "sil",
            "Unresolved Action Ledger entries from crashed session. Review required before next session.")

        print("\n=== CRASH RECOVERY: Unresolved Action Ledger Entries ===", file=sys.stderr)
        print("Skills were in-progress when the session crashed.", file=sys.stderr)
        print("[s]kip  [r]etry after boot  [i]nvestigate (pause)", file=sys.stderr)

        for entry in unresolved:
            skill = entry.get("skill", "?")
            tx = entry.get("tx", "?")
            print(f"\n  Skill: {skill}  (tx: {tx[:8]}...)", file=sys.stderr)
            try:
                with open("/dev/tty") as tty:
                    sys.stderr.write("  Action [s/r/i]: ")
                    sys.stderr.flush()
                    choice = tty.readline().strip().lower()
            except Exception:
                choice = "s"

            if choice == "r":
                self.integrity_log_write("ACTION_LEDGER_RETRY_QUEUED", f"skill={skill} tx={tx}")
                retry_path = self.root / "state" / "pending_retries.jsonl"
                with open(retry_path, "a") as f:
                    json.dump(entry, f)
                    f.write("\n")
            elif choice == "i":
                print("  Investigate. Press Enter to continue.", file=sys.stderr)
                try:
                    with open("/dev/tty") as tty:
                        tty.readline()
                except Exception:
                    pass
            else:
                self.integrity_log_write("ACTION_LEDGER_SKIPPED", f"skill={skill} tx={tx}")

        print("=== Recovery complete ===", file=sys.stderr)

    def _phase4_operator(self):
        op_path = self.root / "memory" / "preferences" / "operator.json"
        imprint = self.root / "memory" / "imprint.json"
        cold_start = not imprint.exists()

        if not op_path.is_file():
            if cold_start:
                # Cold-start: operator not yet enrolled. FAP will handle enrollment.
                self.sil_log("BOOT", "Operator Bound not yet established (cold-start — FAP will enroll).")
                self.integrity_log_write("OPERATOR_BOUND_PENDING", "cold_start")
            else:
                self.sil_log("HALT", "Axiom V: No valid Operator Bound. Entity in permanent inactivity.")
                self.integrity_log_write("OPERATOR_BOUND_INVALID", "boot")
                sys.exit(1)
        else:
            try:
                d = json.loads(op_path.read_text())
                if not (d.get("handle") or d.get("name")):
                    raise ValueError("no handle/name")
            except Exception as e:
                self.sil_log("HALT", f"Axiom V: Operator bound malformed: {e}")
                self.integrity_log_write("OPERATOR_BOUND_INVALID", "boot")
                sys.exit(1)
            self.integrity_log_write("OPERATOR_BOUND_OK", "boot")
            self.sil_log("BOOT", "Operator Bound verified.")

        channel_dir = self.root / self.config.operator_channel_path
        try:
            channel_dir.mkdir(parents=True, exist_ok=True)
            if not os.access(channel_dir, os.W_OK):
                raise PermissionError(f"{channel_dir} not writable")
        except Exception as e:
            self.sil_log("FATAL", f"Operator Channel unverifiable: {e}")
            self.integrity_log_write("OPERATOR_CHANNEL_FAIL", "boot")
            sys.exit(1)

        self.integrity_log_write("OPERATOR_CHANNEL_OK", "boot")
        self.sil_log("BOOT", "Operator Channel verified.")

    def _phase5_fap(self):
        fap_file = self.root / "FIRST_BOOT.md"
        imprint = self.root / "memory" / "imprint.json"

        if not imprint.exists():
            self.sil_log("BOOT", "No Imprint Record — First Activation Protocol.")
            self.integrity_log_write("FAP_DETECTED", "cold_start")
            self.skip_drift = True
            os.environ["FCP_FAP_MODE"] = "true"
            os.environ["FCP_FAP_FILE"] = str(fap_file)
            return

        if fap_file.exists():
            self.sil_log("BOOT", "FIRST_BOOT.md present — FAP mode.")
            self.integrity_log_write("FAP_DETECTED", "first_boot_md")
            self.skip_drift = True
            os.environ["FCP_FAP_MODE"] = "true"
            os.environ["FCP_FAP_FILE"] = str(fap_file)

    def _phase6_critical_check(self):
        if self.skip_drift:
            self.sil_log("BOOT", "Critical condition check skipped (first activation).")
            return
        from core.integrity import check_critical_conditions
        self.sil_log("BOOT", "Checking for unresolved Critical conditions...")
        if not check_critical_conditions(self.root):
            self.integrity_log_write("CRITICAL_CHECK_FAIL", "unresolved_condition")
            self.operator_notify_with_retry("CRITICAL", "sil",
                "Unresolved Critical condition from previous Sleep Cycle. Session token withheld.")
            self.sil_log("FATAL", "Unresolved Critical condition — session blocked. Operator must clear.")
            sys.exit(1)
        self.integrity_log_write("CRITICAL_CHECK_PASS", "boot")
        self.sil_log("BOOT", "No unresolved Critical conditions.")

    def _issue_token(self):
        from core.acp import new_tx
        token = new_tx()
        payload = {"token": token, "issued_at": _ts()}
        _write_json_atomic(self.token_file, payload)
        self.recovery_file.write_text("0")
        self.integrity_log_write("SESSION_OPEN", f"token={token[:8]}")
        self.integrity_log_write("HEARTBEAT_OK", "session_start")
        self.sil_log("SESSION", f"Session token issued: {token[:8]}...")

    # -------------------------------------------------------------------------
    # Session
    # -------------------------------------------------------------------------
    def _session_loop(self):
        self.integrity_log_write("SESSION_LOOP_START", "")
        while True:
            if not self._session_cycle():
                break
            if self.context_critical:
                break

    def _session_cycle(self) -> bool:
        if self.context_critical:
            self.sil_log("SESSION", "Context window critical — closing session.")
            self.integrity_log_write("CONTEXT_WINDOW_CRITICAL", "session_close")
            self.operator_notify("INFO", "sil", "Context window critical — session closed for consolidation.")
            return False

        self.sil_log("SESSION", f"Cognitive cycle {self.cycle_count + 1}...")

        self.mil.drain()

        context = self.cpe.assemble_context(self.mil)

        # Context window critical check
        ctx_size = len(context)
        ctx_critical = self.config.context_budget_chars * self.config.context_window_critical_pct // 100
        if ctx_size >= ctx_critical:
            self.context_critical = True
            self.sil_log("SESSION", f"Context window critical ({ctx_size}/{ctx_critical}).")
            self.integrity_log_write("CONTEXT_WINDOW_CRITICAL", f"size={ctx_size}")
            self.operator_notify("INFO", "sil",
                "Context window critical — session will close after this cycle.")
            return False

        if self.dry_run:
            print(context)
            return False

        output = self.cpe.query(context)

        if not output:
            self.cpe_empty_count += 1
            if self.cpe_empty_count >= self.config.N_retry:
                self.integrity_log_write("CPE_FAILURE", f"no_output_after_{self.config.N_retry}_retries")
                self.operator_notify("WARN", "sil",
                    f"CPE returned no output after {self.config.N_retry} consecutive attempts — session closed.")
                self.sil_log("SESSION", f"CPE returned no output after {self.config.N_retry} attempts. Closing session.")
                return False
            self.sil_log("SESSION", f"CPE returned empty output (attempt {self.cpe_empty_count}/{self.config.N_retry}).")
            self.cycle_count += 1
            self.integrity_log_write("CYCLE_COMPLETE", f"n={self.cycle_count}")
            self.mil.drain()
            return True
        self.cpe_empty_count = 0

        # Print reply to stdout for TUI
        print(output)
        sys.stdout.flush()

        # Log CPE response via ACP
        from core.acp import write as acp_write
        try:
            acp_write("supervisor", "MSG",
                      json.dumps({"role": "assistant", "content": output}),
                      self.root)
        except Exception as e:
            self.sil_log("WARN", f"ACP write failed: {e}")

        # Parse and dispatch actions
        actions = self.cpe.parse_actions(output)
        for action in actions:
            self._dispatch_action(action)

        self.cycle_count += 1
        self.integrity_log_write("CYCLE_COMPLETE", f"n={self.cycle_count}")

        # Heartbeat check
        now = time.time()
        elapsed = now - self.last_vital_check
        if self.cycle_count >= self.config.heartbeat_T or elapsed >= self.config.heartbeat_I:
            self._heartbeat_vital_check()
            self.cycle_count = 0

        self.mil.drain()
        return True

    def _heartbeat_vital_check(self):
        from core.integrity import check_persona_drift
        self.integrity_log_write("HEARTBEAT", f"cycle={self.cycle_count} ts={_ts()}")
        self.sil_log("SESSION", f"Heartbeat Vital Check (cycle={self.cycle_count})...")

        if not check_persona_drift(self.root):
            self.integrity_log_write("IDENTITY_DRIFT_CRITICAL", f"cycle={self.cycle_count}")
            self._revoke_token()
            self.operator_notify_with_retry("CRITICAL", "sil",
                "Axiom II: Identity Drift detected at Heartbeat — session terminated.")
            self.sil_log("FATAL", "Axiom II: Identity Drift → Critical. Session terminated.")
            sys.exit(1)

        self.last_vital_check = time.time()
        self.integrity_log_write("HEARTBEAT_OK", f"cycle={self.cycle_count}")

    def _dispatch_action(self, action: dict):
        atype = action.get("action", "")

        if atype == "skill_request":
            skill = action.get("skill", "")
            params = action.get("params", {})
            self.exec_layer.execute(skill, params)

        elif atype == "evolution_proposal":
            target_file = action.get("target_file", "")
            content = action.get("content", "")
            reason = action.get("reason", "")
            proposal_id = action.get("proposal_id", "") or \
                hashlib.sha256(f"{target_file}:{content}".encode()).hexdigest()[:16]
            content_digest = hashlib.sha256(content.encode()).hexdigest()

            ts = _ts()
            proposals_path = self.root / "state" / "pending_proposals.jsonl"
            record = {
                "proposal_id": proposal_id,
                "ts": ts,
                "target_file": target_file,
                "content": content,
                "reason": reason,
                "content_digest": content_digest,
            }
            with open(proposals_path, "a") as f:
                json.dump(record, f)
                f.write("\n")

            self.integrity_log_write("EVOLUTION_PROPOSAL_PENDING",
                json.dumps({"proposal_id": proposal_id, "content_digest": content_digest}))
            self.sil_log("SESSION", f"Evolution Proposal queued: {proposal_id} → {target_file}")
            self.sil_log("SESSION", f"Awaiting Operator authorization. Run: ./fcp endure approve {proposal_id}")

        elif atype == "session_close":
            payload = {
                "working_memory": action.get("working_memory", []),
                "session_handoff": action.get("session_handoff", {}),
                "consolidation_content": action.get("consolidation_content", ""),
            }
            ts = _ts()
            envelope = {"actor": "cpe", "type": "CLOSURE_PAYLOAD", "ts": ts,
                        "data": json.dumps(payload)}
            inbox = self.root / "memory" / "inbox"
            inbox.mkdir(parents=True, exist_ok=True)
            msg_path = inbox / "closure_payload.msg"
            with open(msg_path, "w") as f:
                json.dump(envelope, f)
                f.write("\n")
            self.context_critical = True

        elif atype in ("reply", "log_note"):
            content = action.get("content", "")
            from core.acp import write as acp_write
            try:
                acp_write("supervisor", "MSG",
                          json.dumps({"role": atype, "content": content}),
                          self.root)
            except Exception:
                pass

        elif atype:
            self.sil_log("WARN", f"Unknown action type: {atype}")

    # -------------------------------------------------------------------------
    # Sleep cycle
    # -------------------------------------------------------------------------
    def _revoke_token(self):
        ts = _ts()
        with open(self.token_file, "a") as f:
            json.dump({"revoked": True, "revoked_at": ts}, f)
            f.write("\n")
        self.integrity_log_write("SESSION_CLOSE", "token_revoked")
        self.sil_log("SESSION", "Session token revoked. Sleep Cycle starting.")

    def _remove_token(self):
        self.token_file.unlink(missing_ok=True)
        self.integrity_log_write("SESSION_TOKEN_REMOVED", "")
        self.sil_log("SLEEP", "Session token artefact removed.")

    def _sleep_stage0_drift(self):
        if self.skip_drift:
            self.sil_log("SLEEP", "Stage 0: Semantic Drift skipped (first activation).")
            return

        from core.integrity import scan_memory_drift
        self.sil_log("SLEEP", "Stage 0: Semantic Drift Detection (two-layer, no LLM)...")
        passed, detail = scan_memory_drift(self.root)

        ts = _ts()
        if passed:
            self.integrity_log_write("DRIFT_OK", "sleep_stage0")
            self.sil_log("SLEEP", "Stage 0: Semantic Drift — all probes passed.")
            self._update_semantic_digest(ts, "PASS", "")
        else:
            self.integrity_log_write("DRIFT_FAULT", detail[:200] if detail else "unspecified_drift")
            self.operator_notify_with_retry("CRITICAL", "sil",
                "Axiom II: Semantic Drift detected in Sleep Cycle Stage 0. Next session blocked.")
            self.sil_log("SLEEP", "Stage 0: DRIFT_FAULT logged. Next boot Phase 6 will withhold token.")
            self._update_semantic_digest(ts, "DRIFT_FAULT", detail)

    def _update_semantic_digest(self, ts: str, result: str, detail: str):
        try:
            d = json.loads(self.semantic_digest.read_text()) if self.semantic_digest.exists() else {}
        except Exception:
            d = {}
        history = d.get("history", [])
        entry = {"ts": ts, "result": result}
        if detail:
            entry["detail"] = detail[:200]
        history.append(entry)
        d["history"] = history[-50:]
        d["last_updated"] = ts
        d["last_result"] = result
        _write_json_atomic(self.semantic_digest, d)

    def _sleep_stage3_endure(self):
        from core.integrity import endure_execute
        self.sil_log("SLEEP", "Stage 3: Endure Execution...")

        proposals_path = self.root / "state" / "pending_proposals.jsonl"
        if proposals_path.exists() and proposals_path.stat().st_size > 0:
            self.sil_log("SLEEP", "Stage 3: Processing authorized Evolution Proposals...")
            messages = endure_execute(self.root)
            for msg in messages:
                self.sil_log("SLEEP", msg)
        else:
            self.sil_log("SLEEP", "Stage 3: No queued Evolution Proposals.")

        self.integrity_log_write("SLEEP_COMPLETE", "")
        self.sil_log("SLEEP", "SLEEP_COMPLETE record written.")
        self._remove_token()

    def _sleep_cycle(self):
        self.sil_log("SLEEP", "Sleep Cycle starting...")
        self.integrity_log_write("SLEEP_CYCLE_START", "")

        self._sleep_stage0_drift()

        self.sil_log("SLEEP", "Stage 1: Memory Consolidation...")
        self.mil.stage1_consolidate()

        self.sil_log("SLEEP", "Stage 2: Garbage Collection...")
        self.mil.stage2_gc()

        self._sleep_stage3_endure()

        self.sil_log("SLEEP", "Sleep Cycle complete.")

    # -------------------------------------------------------------------------
    # Main
    # -------------------------------------------------------------------------
    def _init_subsystems(self):
        from core.acp import new_tx
        from core.mil import MIL
        from core.exec_layer import ExecLayer
        from core.cpe import CPE

        self.mil = MIL(self.root, self.config)
        self.exec_layer = ExecLayer(self.root, self.config)
        self.cpe = CPE(self.root, self.config)

    def run(self) -> int:
        self._prereq_beacon()
        self._phase0_sandbox()
        self._phase1_baseline()
        self._init_subsystems()
        self._phase2_integrity()
        self._phase3_crash_recovery()
        self._phase4_operator()
        self._phase5_fap()
        self._phase6_critical_check()
        self._issue_token()

        self._session_loop()

        self._revoke_token()
        self._sleep_cycle()

        self.integrity_log_write("BOOT_COMPLETE", "")
        self.sil_log("BOOT", "Process complete.")
        return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _endure_list(root: Path):
    proposals_path = root / "state" / "pending_proposals.jsonl"
    if not proposals_path.exists():
        print("No pending Evolution Proposals.")
        return

    proposals = []
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
        print("No pending Evolution Proposals.")
        return

    log_path = root / "state" / "integrity.log"
    auth_ids = set()
    if log_path.exists():
        with open(log_path) as f:
            for line in f:
                try:
                    e = json.loads(line.strip())
                    if e.get("type") == "EVOLUTION_AUTH" or e.get("event") == "EVOLUTION_AUTH":
                        d_raw = e.get("data", "{}")
                        d = json.loads(d_raw) if isinstance(d_raw, str) else d_raw
                        auth_ids.add(d.get("proposal_id", ""))
                except Exception:
                    pass

    print(f"{'ID':<20} {'STATUS':<12} {'FILE':<40} REASON")
    print("-" * 90)
    for p in proposals:
        pid = p.get("proposal_id", "")[:18]
        status = "AUTHORIZED" if p.get("proposal_id", "") in auth_ids else "PENDING"
        tgt = p.get("target_file", "")[:38]
        reason = p.get("reason", "")[:30]
        print(f"{pid:<20} {status:<12} {tgt:<40} {reason}")


def _endure_approve(root: Path, proposal_id: str):
    proposals_path = root / "state" / "pending_proposals.jsonl"
    log_path = root / "state" / "integrity.log"

    proposal = None
    if proposals_path.exists():
        with open(proposals_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    p = json.loads(line)
                    if p.get("proposal_id") == proposal_id:
                        proposal = p
                        break
                except Exception:
                    pass

    if not proposal:
        print(f"Proposal not found: {proposal_id}", file=sys.stderr)
        sys.exit(1)

    print(f"\n=== Evolution Proposal: {proposal_id} ===")
    print(f"Target:  {proposal.get('target_file', '')}")
    print(f"Reason:  {proposal.get('reason', '')}")
    print(f"Digest:  {proposal.get('content_digest', '')}")
    print(f"\n--- Proposed content ---")
    print(proposal.get("content", ""))
    print("---")

    try:
        with open("/dev/tty") as tty:
            sys.stdout.write("\nApprove this proposal? [y/N] ")
            sys.stdout.flush()
            answer = tty.readline().strip().lower()
    except Exception:
        answer = ""

    if answer != "y":
        print("Proposal not approved.")
        return

    op_path = root / "memory" / "preferences" / "operator.json"
    operator = "operator"
    try:
        op = json.loads(op_path.read_text())
        operator = op.get("handle") or op.get("name", "operator")
    except Exception:
        pass

    ts = _ts()
    auth_data = json.dumps({
        "proposal_id": proposal_id,
        "content_digest": proposal.get("content_digest", ""),
        "operator": operator,
        "approved_at": ts,
    })
    entry = {"actor": "sil", "type": "EVOLUTION_AUTH", "ts": ts, "data": auth_data}
    with open(log_path, "a") as f:
        json.dump(entry, f)
        f.write("\n")

    print(f"EVOLUTION_AUTH written for {proposal_id}.")
    print(f"Proposal will execute at next Sleep Cycle Stage 3.")


if __name__ == "__main__":
    # Locate root
    script_dir = Path(__file__).resolve().parent
    root = script_dir.parent
    os.environ.setdefault("FCP_REF_ROOT", str(root))

    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    skip_drift = "--skip-drift" in args
    args = [a for a in args if a not in ("--dry-run", "--skip-drift")]

    if args and args[0] == "endure":
        sub = args[1] if len(args) > 1 else ""
        if sub == "list":
            _endure_list(root)
        elif sub == "approve" and len(args) > 2:
            _endure_approve(root, args[2])
        else:
            print("Usage: sil.py endure {list|approve <proposal_id>}", file=sys.stderr)
            sys.exit(1)
    else:
        sil = SIL(root, dry_run=dry_run, skip_drift=skip_drift)
        sys.exit(sil.run())
