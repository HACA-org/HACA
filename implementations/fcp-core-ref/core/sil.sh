#!/bin/bash
# core/sil.sh — System Integrity Layer (HACA-Arch §4.4 / HACA-Core 1.0.0)
# Boot sequencer, integrity authority, and session token gatekeeper.
#
# Boot sequence (FCP-Core §6):
#   Prereq  — Passive Distress Beacon check
#   Phase 0 — Sandbox / CPE topology enforcement   (Axiom I)
#   Phase 1 — Structural baseline load
#   Phase 2 — Integrity Document validation        (Axiom II)
#   Phase 3 — Crash recovery                       (§5.1)
#   Phase 4 — Operator Bound + Channel verification (Axiom V / §5.3)
#   Phase 5 — First Activation Protocol            (if cold-start)
#   Phase 6 — Critical Condition Check             (unresolved DRIFT_FAULT)
#   Token   — Session token issued                 (Phase 7)
#   Cycle   — Cognitive cycle loop
#   Token   — Session token REVOKED (marked, artefact kept)
#
# Sleep Cycle (FCP-Core §6b):
#   Stage 0 — Semantic Drift Detection             (no LLM, two-layer probes)
#   Stage 1 — Memory Consolidation                 (Closure Payload → MIL)
#   Stage 2 — Garbage Collection                   (GC pass)
#   Stage 3 — Endure Execution                     (Evolution Proposals)
#   SLEEP_COMPLETE written → token artefact removed

set -euo pipefail

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------
if [ -z "${FCP_REF_ROOT:-}" ]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    export FCP_REF_ROOT="$(dirname "$SCRIPT_DIR")"
fi

MIL="$FCP_REF_ROOT/core/mil.sh"
EXEC="$FCP_REF_ROOT/core/exec.sh"
CPE="$FCP_REF_ROOT/core/cpe.sh"
SIL_HELPERS="$FCP_REF_ROOT/core/sil_helpers.py"

source "$FCP_REF_ROOT/skills/lib/acp.sh"
source "$FCP_REF_ROOT/skills/lib/rotation.sh"

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
TOKEN_FILE="$FCP_REF_ROOT/state/sentinels/session.token"
BASELINE_FILE="$FCP_REF_ROOT/state/baseline.json"
INTEGRITY_LOG="$FCP_REF_ROOT/state/integrity.log"
RECOVERY_FILE="$FCP_REF_ROOT/state/sentinels/recovery.attempts"
BEACON_FILE="$FCP_REF_ROOT/state/distress.beacon"
SEMANTIC_DIGEST="$FCP_REF_ROOT/state/semantic-digest.json"

# Populated by phase1_baseline
N_BOOT=3
N_CHANNEL=3
N_RETRY=3
I_SECONDS=300
HEARTBEAT_T=10
S_BYTES=10485760
C_COMMITS=10
CHANNEL_PATH="state/operator_notifications"

# Runtime
DRY_RUN=false
SKIP_DRIFT=false
CYCLE_COUNT=0
LAST_VITAL_CHECK=0

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
sil_log()      { echo "[SIL:$1] $2" >&2; }
baseline_get() { python3 "$SIL_HELPERS" baseline-get "$1"; }

integrity_log() {
    local component="$1" event="$2" detail="${3:-}"
    local ts
    ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    printf '{"ts":"%s","component":"%s","event":"%s","detail":"%s"}\n' \
        "$ts" "$component" "$event" "$detail" >> "$INTEGRITY_LOG"
}

# ---------------------------------------------------------------------------
# Operator Channel  (HACA-Core §5.3)
# ---------------------------------------------------------------------------
operator_notify() {
    local severity="$1" component="$2" message="$3"
    local channel_dir="$FCP_REF_ROOT/$CHANNEL_PATH"
    local ts filename
    ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    filename="${channel_dir}/$(date -u +%Y%m%dT%H%M%SZ)_${severity}_${component}.json"
    if printf '{"ts":"%s","severity":"%s","component":"%s","message":"%s"}\n' \
        "$ts" "$severity" "$component" "$message" > "$filename"; then
        integrity_log "sil" "OPERATOR_CHANNEL_SENT" "severity=$severity"
        sil_log "CHANNEL" "[$severity] $component: $message"
        return 0
    fi
    integrity_log "sil" "OPERATOR_CHANNEL_FAIL" "severity=$severity"
    return 1
}

operator_notify_with_retry() {
    local severity="$1" component="$2" message="$3"
    local attempt=0
    while [ "$attempt" -lt "$N_CHANNEL" ]; do
        operator_notify "$severity" "$component" "$message" && return 0
        attempt=$((attempt + 1))
        sil_log "CHANNEL" "Attempt $attempt/$N_CHANNEL failed."
    done
    sil_log "FATAL" "Operator Channel exhausted after $N_CHANNEL attempts."
    distress_beacon_activate "operator_channel_failure"
    exit 1
}

# ---------------------------------------------------------------------------
# Passive Distress Beacon  (HACA-Core §5.4)
# ---------------------------------------------------------------------------
distress_beacon_activate() {
    local reason="$1"
    local ts
    ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    printf '{"active":true,"activated_at":"%s","reason":"%s"}\n' \
        "$ts" "$reason" > "$BEACON_FILE"
    integrity_log "sil" "DISTRESS_BEACON_ACTIVATED" "$reason"
    sil_log "BEACON" "Distress Beacon activated: $reason"
}

# ---------------------------------------------------------------------------
# PREREQUISITE — Passive Distress Beacon check
# Active beacon → suspended halt, no gate runs, no token issued.
# ---------------------------------------------------------------------------
prereq_beacon() {
    [ -f "$BEACON_FILE" ] || return 0
    sil_log "HALT" "Passive Distress Beacon is active. Resolve the condition first."
    sil_log "HALT" "Then: rm $BEACON_FILE"
    exit 1
}

# ---------------------------------------------------------------------------
# Phase 0 — Sandbox / CPE topology enforcement  (HACA-Core Axiom I)
# Transparent topology required. Verifies confinement.
# ---------------------------------------------------------------------------
phase0_sandbox() {
    # CPE topology: baseline must declare "transparent"
    local topology
    topology=$(baseline_get topology 2>/dev/null || echo "")
    if [ "$topology" != "transparent" ]; then
        sil_log "FATAL" "Axiom I: Declared topology '$topology' is not 'transparent'. Boot aborted."
        exit 1
    fi

    # Confinement verification
    if [ "$$" -eq 1 ] || grep -qaE 'docker|lxc|containerd|libpod' /proc/1/cgroup 2>/dev/null; then
        sil_log "BOOT" "Confinement verified (container environment)."
        return 0
    fi
    if command -v unshare >/dev/null 2>&1; then
        sil_log "BOOT" "Re-executing inside private namespace..."
        exec unshare -m -p -f -r --mount-proc "$0" "$@"
    fi
    # Fallback: write-boundary test
    local test_file="/tmp/fcp_boundary_test_$$"
    if touch "$test_file" 2>/dev/null; then
        rm -f "$test_file"
        sil_log "WARN" "Namespace isolation unavailable; boundary test passed."
        return 0
    fi
    sil_log "FATAL" "Axiom I: Confinement Fault — unshare unavailable and boundary test failed."
    exit 1
}

# ---------------------------------------------------------------------------
# Phase 1 — Load structural baseline
# ---------------------------------------------------------------------------
phase1_baseline() {
    [ -f "$BASELINE_FILE" ] || { sil_log "FATAL" "Baseline missing: $BASELINE_FILE"; exit 1; }
    N_BOOT=$(baseline_get thresholds.N_boot)
    N_CHANNEL=$(baseline_get thresholds.N_channel)
    N_RETRY=$(baseline_get thresholds.N_retry)
    S_BYTES=$(baseline_get thresholds.S_bytes)
    C_COMMITS=$(baseline_get integrity_chain.checkpoint_interval_C)
    I_SECONDS=$(baseline_get heartbeat.I_seconds)
    HEARTBEAT_T=$(baseline_get heartbeat.T)
    CHANNEL_PATH=$(baseline_get operator_channel.path)
    mkdir -p "$FCP_REF_ROOT/$CHANNEL_PATH"
    mkdir -p "$(dirname "$TOKEN_FILE")"
    sil_log "BOOT" "Structural baseline loaded."
}

# ---------------------------------------------------------------------------
# Phase 2 — Integrity Document validation  (HACA-Core Axiom II)
# ---------------------------------------------------------------------------
phase2_integrity() {
    sil_log "BOOT" "Verifying Integrity Document..."
    if ! python3 "$SIL_HELPERS" verify-integrity; then
        integrity_log "sil" "INTEGRITY_MISMATCH" "boot"
        sil_log "FATAL" "Integrity mismatch — Axiom II Violation. Boot aborted."
        exit 1
    fi
    integrity_log "sil" "INTEGRITY_OK" "boot"
}

# ---------------------------------------------------------------------------
# Phase 3 — Crash recovery  (HACA-Core §5.1)
# Stale token artefact = crash or incomplete Sleep Cycle indicator.
# ---------------------------------------------------------------------------
phase3_crash_recovery() {
    local crash_count=0
    [ -f "$RECOVERY_FILE" ] && crash_count=$(cat "$RECOVERY_FILE" 2>/dev/null || echo 0)

    if [ ! -f "$TOKEN_FILE" ]; then
        echo "0" > "$RECOVERY_FILE"
        return 0
    fi

    sil_log "RECOVERY" "Stale session token — crash or incomplete Sleep Cycle detected."
    integrity_log "sil" "CRASH_DETECTED" "stale_token"
    crash_count=$((crash_count + 1))
    echo "$crash_count" > "$RECOVERY_FILE"

    if [ "$crash_count" -ge "$N_BOOT" ]; then
        sil_log "FATAL" "Boot loop: $crash_count crashes (N_boot=$N_BOOT)."
        distress_beacon_activate "boot_loop_$crash_count"
        operator_notify_with_retry "CRITICAL" "sil" \
            "Boot loop: $crash_count consecutive crashes. Beacon activated."
        exit 1
    fi

    operator_notify "WARN" "sil" "Crash recovery boot $crash_count of $N_BOOT."
    review_action_ledger
    rm -f "$TOKEN_FILE"
    sil_log "RECOVERY" "Stale token cleared."
}

review_action_ledger() {
    local unresolved_file
    unresolved_file=$(mktemp)
    python3 "$SIL_HELPERS" find-unresolved-ledger > "$unresolved_file"

    if [ ! -s "$unresolved_file" ]; then
        sil_log "RECOVERY" "Action Ledger: no unresolved entries."
        rm -f "$unresolved_file"
        return 0
    fi

    sil_log "RECOVERY" "Unresolved Action Ledger entries — Operator review required."
    integrity_log "sil" "ACTION_LEDGER_UNRESOLVED" "see_operator_notifications"
    operator_notify "CRITICAL" "sil" \
        "Unresolved Action Ledger entries from crashed session. Review required before next session."

    echo ""
    echo "=== CRASH RECOVERY: Unresolved Action Ledger Entries ==="
    echo "Skills were in-progress when the session crashed."
    echo "[s]kip  [r]etry after boot  [i]nvestigate (pause)"
    echo ""

    while IFS= read -r entry; do
        [ -z "$entry" ] && continue
        local skill tx
        skill=$(python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('skill','?'))" "$entry")
        tx=$(python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('tx','?'))" "$entry")
        echo "  Skill: $skill  (tx: ${tx:0:8}...)"
        printf "  Action [s/r/i]: "
        local choice
        read -r choice </dev/tty || choice="s"
        case "$choice" in
            r)  integrity_log "sil" "ACTION_LEDGER_RETRY_QUEUED" "skill=$skill tx=$tx"
                echo "$entry" >> "$FCP_REF_ROOT/state/pending_retries.jsonl" ;;
            i)  echo "  Investigate. Press Enter to continue."; read -r _ </dev/tty || true ;;
            *)  integrity_log "sil" "ACTION_LEDGER_SKIPPED" "skill=$skill tx=$tx" ;;
        esac
    done < "$unresolved_file"

    rm -f "$unresolved_file"
    echo "=== Recovery complete ==="
}

# ---------------------------------------------------------------------------
# Phase 4 — Operator Bound + Operator Channel verification
# (HACA-Core Axiom V, §5.3)
# ---------------------------------------------------------------------------
phase4_operator() {
    # Operator Bound
    if ! python3 "$SIL_HELPERS" verify-operator-bound; then
        sil_log "HALT" "Axiom V: No valid Operator Bound. Entity in permanent inactivity."
        integrity_log "sil" "OPERATOR_BOUND_INVALID" "boot"
        exit 1
    fi
    integrity_log "sil" "OPERATOR_BOUND_OK" "boot"
    sil_log "BOOT" "Operator Bound verified."

    # Operator Channel reachability
    local channel_dir="$FCP_REF_ROOT/$CHANNEL_PATH"
    if ! mkdir -p "$channel_dir" 2>/dev/null || [ ! -w "$channel_dir" ]; then
        sil_log "FATAL" "Operator Channel unverifiable: $channel_dir is not writable."
        integrity_log "sil" "OPERATOR_CHANNEL_FAIL" "boot"
        exit 1
    fi
    integrity_log "sil" "OPERATOR_CHANNEL_OK" "boot"
    sil_log "BOOT" "Operator Channel verified."
}

# ---------------------------------------------------------------------------
# Phase 5 — First Activation Protocol  (FCP-Core §6a)
# Cold-start indicator: absence of memory/imprint.json.
# ---------------------------------------------------------------------------
phase5_fap() {
    local fap_file="$FCP_REF_ROOT/FIRST_BOOT.md"
    local imprint="$FCP_REF_ROOT/memory/imprint.json"

    # Cold-start: imprint absent
    if [ ! -f "$imprint" ]; then
        sil_log "BOOT" "No Imprint Record — First Activation Protocol."
        integrity_log "sil" "FAP_DETECTED" "cold_start"
        SKIP_DRIFT=true
        export FCP_FAP_MODE=true
        export FCP_FAP_FILE="${fap_file}"
        return 0
    fi

    # Legacy: FIRST_BOOT.md present (operator placed it manually)
    if [ -f "$fap_file" ]; then
        sil_log "BOOT" "FIRST_BOOT.md present — FAP mode."
        integrity_log "sil" "FAP_DETECTED" "first_boot_md"
        SKIP_DRIFT=true
        export FCP_FAP_MODE=true
        export FCP_FAP_FILE="$fap_file"
    fi
}

# ---------------------------------------------------------------------------
# Phase 6 — Critical Condition Check  (FCP-Core §6, Phase 6)
# Checks Integrity Log for unresolved DRIFT_FAULT or ESCALATION_FAILED records.
# These are written by Sleep Cycle Stage 0 and cleared only by explicit Operator action.
# ---------------------------------------------------------------------------
phase6_critical_check() {
    if [ "$SKIP_DRIFT" = "true" ]; then
        sil_log "BOOT" "Critical condition check skipped (first activation)."
        return 0
    fi
    sil_log "BOOT" "Checking for unresolved Critical conditions..."
    if ! python3 "$SIL_HELPERS" check-critical-conditions; then
        integrity_log "sil" "CRITICAL_CHECK_FAIL" "unresolved_condition"
        operator_notify_with_retry "CRITICAL" "sil" \
            "Unresolved Critical condition from previous Sleep Cycle. Session token withheld."
        sil_log "FATAL" "Unresolved Critical condition — session blocked. Operator must clear."
        exit 1
    fi
    integrity_log "sil" "CRITICAL_CHECK_PASS" "boot"
    sil_log "BOOT" "No unresolved Critical conditions."
}

# ---------------------------------------------------------------------------
# Session Token  (FCP-Core §6, Phase 7 / §6b)
# issue_token   — writes token artefact; marks session start
# revoke_token  — marks token as revoked (keeps artefact as crash indicator)
# remove_token  — deletes artefact; called only after SLEEP_COMPLETE
# ---------------------------------------------------------------------------
issue_token() {
    local token
    token=$(acp_new_tx)
    printf '{"token":"%s","issued_at":"%s"}\n' \
        "$token" "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" > "$TOKEN_FILE"
    echo "0" > "$RECOVERY_FILE"
    integrity_log "sil" "SESSION_OPEN" "token=${token:0:8}"
    sil_log "SESSION" "Session token issued: ${token:0:8}..."
}

revoke_token() {
    local ts
    ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    # Append revocation marker — artefact kept as crash indicator during Sleep Cycle
    printf '{"revoked":true,"revoked_at":"%s"}\n' "$ts" >> "$TOKEN_FILE"
    integrity_log "sil" "SESSION_CLOSE" "token_revoked"
    sil_log "SESSION" "Session token revoked. Sleep Cycle starting."
}

remove_token() {
    rm -f "$TOKEN_FILE"
    integrity_log "sil" "SESSION_TOKEN_REMOVED" ""
    sil_log "SLEEP" "Session token artefact removed."
}

# ---------------------------------------------------------------------------
# Heartbeat Vital Check  (HACA-Core §4.2)
# Identity Drift: persona hashes vs Integrity Document.
# ---------------------------------------------------------------------------
heartbeat_vital_check() {
    local ts
    ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    integrity_log "sil" "HEARTBEAT" "cycle=$CYCLE_COUNT ts=$ts"
    sil_log "SESSION" "Heartbeat Vital Check (cycle=$CYCLE_COUNT)..."

    if ! python3 "$SIL_HELPERS" check-persona-drift; then
        integrity_log "sil" "IDENTITY_DRIFT_CRITICAL" "cycle=$CYCLE_COUNT"
        revoke_token
        operator_notify_with_retry "CRITICAL" "sil" \
            "Axiom II: Identity Drift detected at Heartbeat — session terminated."
        sil_log "FATAL" "Axiom II: Identity Drift → Critical. Session terminated."
        exit 1
    fi

    LAST_VITAL_CHECK=$(date +%s)
    integrity_log "sil" "HEARTBEAT_OK" "cycle=$CYCLE_COUNT"
}

# ---------------------------------------------------------------------------
# Session Cycle  (HACA-Arch §6.3)
# Returns 1 to signal session-close.
# ---------------------------------------------------------------------------
session_cycle() {
    sil_log "SESSION" "Cognitive cycle $((CYCLE_COUNT + 1))..."

    # CPE already signaled context-critical in previous cycle
    if [ "${FCP_CONTEXT_CRITICAL:-false}" = "true" ]; then
        sil_log "SESSION" "Context window critical — closing session."
        integrity_log "sil" "CONTEXT_WINDOW_CRITICAL" "session_close"
        operator_notify "INFO" "sil" \
            "Context window critical — session closed for consolidation."
        return 1
    fi

    "$MIL" drain

    local context
    context=$("$CPE" context)

    # Context window critical check
    local ctx_size budget ctx_pct ctx_critical
    ctx_size=${#context}
    budget=$(baseline_get thresholds.context_budget_chars 2>/dev/null || echo 600000)
    ctx_pct=$(baseline_get thresholds.context_window_critical_pct)
    ctx_critical=$(( budget * ctx_pct / 100 ))
    if [ "$ctx_size" -ge "$ctx_critical" ]; then
        export FCP_CONTEXT_CRITICAL=true
        sil_log "SESSION" "Context window critical (${ctx_size}/${ctx_critical})."
        integrity_log "sil" "CONTEXT_WINDOW_CRITICAL" "size=${ctx_size}"
        operator_notify "INFO" "sil" \
            "Context window critical — session will close after this cycle."
        return 1
    fi

    if [ "$DRY_RUN" = "true" ]; then
        echo "$context"
        return 1  # signal session close after printing context
    fi

    local output
    output=$("$CPE" query "$context")

    # Log CPE response
    local response_json
    response_json=$(python3 -c \
        "import json,sys; print(json.dumps({'role':'assistant','content':sys.argv[1]}))" \
        "$output")
    acp_write "supervisor" "MSG" "$response_json" >/dev/null

    # Parse and dispatch actions (SIL mediates all host actuation — Axiom I)
    local actions
    actions=$("$CPE" parse "$output")

    while IFS= read -r action; do
        [ -z "$action" ] && continue
        local atype
        atype=$(python3 -c \
            "import json,sys; print(json.loads(sys.argv[1]).get('action',''))" \
            "$action" 2>/dev/null || echo "")

        case "$atype" in
            skill_request)
                local skill params
                skill=$(python3 -c \
                    "import json,sys; print(json.loads(sys.argv[1]).get('skill',''))" "$action")
                params=$(python3 -c \
                    "import json,sys; print(json.dumps(json.loads(sys.argv[1]).get('params',{})))" \
                    "$action")
                "$EXEC" execute "$skill" "$params"
                ;;
            evolution_proposal)
                # HACA-Core §4.5: hold pending explicit Operator approval. Never auto-queue.
                # Outcome never returned to CPE.
                python3 - "$action" <<'PYEOF'
import hashlib, json, os, sys
from datetime import datetime, timezone

root = os.environ.get("FCP_REF_ROOT", "")
try:
    d = json.loads(sys.argv[1])
except Exception:
    d = {}

target_file   = d.get("target_file", "")
content       = d.get("content", "")
reason        = d.get("reason", "")
proposal_id   = d.get("proposal_id", "") or \
    hashlib.sha256(f"{target_file}:{content}".encode()).hexdigest()[:16]
content_digest = hashlib.sha256(content.encode()).hexdigest()

ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

# Write to pending_proposals.jsonl
proposals_path = os.path.join(root, "state", "pending_proposals.jsonl")
record = {
    "proposal_id":    proposal_id,
    "ts":             ts,
    "target_file":    target_file,
    "content":        content,
    "reason":         reason,
    "content_digest": content_digest,
}
with open(proposals_path, "a") as f:
    json.dump(record, f)
    f.write("\n")

# Log to integrity.log via stdout (picked up by integrity_log caller)
# We print directly since we're inside a python3 - heredoc
log_path = os.path.join(root, "state", "integrity.log")
log_entry = {
    "actor": "sil",
    "type":  "EVOLUTION_PROPOSAL_PENDING",
    "ts":    ts,
    "data":  json.dumps({"proposal_id": proposal_id, "content_digest": content_digest}),
}
with open(log_path, "a") as f:
    json.dump(log_entry, f)
    f.write("\n")

print(f"[SIL] Evolution Proposal queued: {proposal_id} → {target_file}", file=sys.stderr)
print(f"[SIL] Awaiting Operator authorization. Run: ./fcp endure approve {proposal_id}", file=sys.stderr)
PYEOF
                ;;
            session_close)
                # Extract Closure Payload from action and write to inbox
                python3 - "$action" <<'PYEOF'
import json, os, sys
from datetime import datetime, timezone

root = os.environ.get("FCP_REF_ROOT", "")
try:
    d = json.loads(sys.argv[1])
except Exception:
    d = {}

payload = {
    "working_memory":       d.get("working_memory", []),
    "session_handoff":      d.get("session_handoff", {}),
    "consolidation_content": d.get("consolidation_content", ""),
}
ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
envelope = {
    "actor": "cpe",
    "type":  "CLOSURE_PAYLOAD",
    "ts":    ts,
    "data":  json.dumps(payload),
}
inbox = os.path.join(root, "memory", "inbox")
os.makedirs(inbox, exist_ok=True)
msg_path = os.path.join(inbox, "closure_payload.msg")
with open(msg_path, "w") as f:
    json.dump(envelope, f)
    f.write("\n")
PYEOF
                export FCP_CONTEXT_CRITICAL=true
                ;;
            log_note | reply)
                local content
                content=$(python3 -c \
                    "import json,sys; print(json.loads(sys.argv[1]).get('content',''))" "$action")
                acp_write "supervisor" "MSG" \
                    "{\"role\":\"$atype\",\"content\":$(python3 -c \
                    'import json,sys; print(json.dumps(sys.argv[1]))' "$content")}" >/dev/null
                ;;
            *)
                [ -n "$atype" ] && sil_log "WARN" "Unknown action type: $atype"
                ;;
        esac
    done <<< "$actions"

    CYCLE_COUNT=$((CYCLE_COUNT + 1))
    integrity_log "sil" "CYCLE_COMPLETE" "n=$CYCLE_COUNT"

    # Heartbeat: fire on T cycles or I seconds elapsed
    local now elapsed
    now=$(date +%s)
    elapsed=$((now - LAST_VITAL_CHECK))
    if [ "$CYCLE_COUNT" -ge "$HEARTBEAT_T" ] || [ "$elapsed" -ge "$I_SECONDS" ]; then
        heartbeat_vital_check
        CYCLE_COUNT=0
    fi

    "$MIL" drain
}

# ---------------------------------------------------------------------------
# Sleep Cycle — Stage 0: Semantic Drift Detection  (FCP-Core §6b Stage 0)
# Runs two-layer Semantic Probes against Memory Store content.
# No LLM invocation. CPE is inactive at this stage.
# Drift → log DRIFT_FAULT Critical to Integrity Log + notify Operator.
# Does NOT halt Sleep Cycle — stages 1-3 still complete.
# ---------------------------------------------------------------------------
sleep_stage0_drift() {
    if [ "$SKIP_DRIFT" = "true" ]; then
        sil_log "SLEEP" "Stage 0: Semantic Drift skipped (first activation)."
        return 0
    fi

    sil_log "SLEEP" "Stage 0: Semantic Drift Detection (two-layer, no LLM)..."

    local drift_output
    if drift_output=$(python3 "$SIL_HELPERS" scan-memory-drift 2>/dev/null); then
        integrity_log "sil" "DRIFT_OK" "sleep_stage0"
        sil_log "SLEEP" "Stage 0: Semantic Drift — all probes passed."
    else
        # Drift detected — log Critical condition, notify Operator
        # Do NOT halt: remaining stages still execute
        local fault_detail="${drift_output:-unspecified_drift}"
        integrity_log "sil" "DRIFT_FAULT" "$fault_detail"
        operator_notify_with_retry "CRITICAL" "sil" \
            "Axiom II: Semantic Drift detected in Sleep Cycle Stage 0. Next session blocked."
        sil_log "SLEEP" "Stage 0: DRIFT_FAULT logged. Next boot Phase 6 will withhold token."

        # Update Semantic Digest with drift result
        local ts
        ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
        python3 - <<PYEOF
import json, os

digest_path = "$SEMANTIC_DIGEST"
ts = "$ts"
fault = """$fault_detail"""

try:
    d = json.load(open(digest_path)) if os.path.exists(digest_path) else {}
except Exception:
    d = {}

history = d.get("history", [])
history.append({"ts": ts, "result": "DRIFT_FAULT", "detail": fault[:200]})
d["history"] = history[-50:]  # keep last 50 cycles
d["last_updated"] = ts
d["last_result"] = "DRIFT_FAULT"

tmp = digest_path + ".tmp"
with open(tmp, "w") as f:
    json.dump(d, f, indent=2)
os.replace(tmp, digest_path)
PYEOF
        return 0  # Do not propagate — stages 1-3 still run
    fi

    # Update Semantic Digest with pass result
    local ts
    ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    python3 - <<PYEOF
import json, os

digest_path = "$SEMANTIC_DIGEST"
ts = "$ts"

try:
    d = json.load(open(digest_path)) if os.path.exists(digest_path) else {}
except Exception:
    d = {}

history = d.get("history", [])
history.append({"ts": ts, "result": "PASS"})
d["history"] = history[-50:]
d["last_updated"] = ts
d["last_result"] = "PASS"

tmp = digest_path + ".tmp"
with open(tmp, "w") as f:
    json.dump(d, f, indent=2)
os.replace(tmp, digest_path)
PYEOF
}

# ---------------------------------------------------------------------------
# Sleep Cycle — Stage 3: Endure Execution  (FCP-Core §6b Stage 3)
# Executes queued, Operator-authorized Evolution Proposals.
# Writes SLEEP_COMPLETE record. Removes session token artefact.
# ---------------------------------------------------------------------------
sleep_stage3_endure() {
    sil_log "SLEEP" "Stage 3: Endure Execution..."

    local pending_proposals="$FCP_REF_ROOT/state/pending_proposals.jsonl"
    if [ -f "$pending_proposals" ] && [ -s "$pending_proposals" ]; then
        sil_log "SLEEP" "Stage 3: Processing authorized Evolution Proposals..."
        python3 "$SIL_HELPERS" endure-execute 2>&1 | while IFS= read -r line; do
            sil_log "SLEEP" "$line"
        done
    else
        sil_log "SLEEP" "Stage 3: No queued Evolution Proposals."
    fi

    integrity_log "sil" "SLEEP_COMPLETE" ""
    sil_log "SLEEP" "SLEEP_COMPLETE record written."

    remove_token
}

# ---------------------------------------------------------------------------
# Sleep Cycle  (FCP-Core §6b)
# Orchestrates Stages 0-3 in order. Each stage must complete before the next.
# Token revocation happens before Stage 0; removal happens after Stage 3.
# ---------------------------------------------------------------------------
sleep_cycle() {
    sil_log "SLEEP" "Sleep Cycle starting..."
    integrity_log "sil" "SLEEP_CYCLE_START" ""

    sleep_stage0_drift

    sil_log "SLEEP" "Stage 1: Memory Consolidation..."
    "$MIL" stage1

    sil_log "SLEEP" "Stage 2: Garbage Collection..."
    "$MIL" stage2

    sleep_stage3_endure

    sil_log "SLEEP" "Sleep Cycle complete."
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
# Save original args before parsing (needed for re-execution in phase0_sandbox)
ORIG_ARGS=("$@")

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)    DRY_RUN=true;    shift ;;
        --skip-drift) SKIP_DRIFT=true; shift ;;
        *) shift ;;
    esac
done

LAST_VITAL_CHECK=$(date +%s)

prereq_beacon
phase0_sandbox "${ORIG_ARGS[@]}"
phase1_baseline
phase2_integrity
phase3_crash_recovery
phase4_operator
phase5_fap
phase6_critical_check
issue_token

integrity_log "sil" "SESSION_LOOP_START" ""

while true; do
    if ! session_cycle; then
        break
    fi
    # Check if CPE requested session close
    [ "${FCP_CONTEXT_CRITICAL:-false}" = "true" ] && break
done

revoke_token
sleep_cycle

integrity_log "sil" "BOOT_COMPLETE" ""
sil_log "BOOT" "Process complete."
