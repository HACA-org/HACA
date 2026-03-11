#!/bin/bash
# core/sil.sh — System Integrity Layer (HACA-Arch §4.4 / HACA-Core 1.0.0)
# Boot sequencer, integrity authority, and session token gatekeeper.
#
# Boot sequence:
#   Phase 0  — Sandbox / Topology enforcement  (Axiom I)
#   Phase 1  — Structural baseline load
#   Phase 2  — Integrity Document validation   (Axiom II)
#   Phase 3  — Distress Beacon check
#   Phase 4  — Crash recovery
#   Phase 5  — Operator Bound verification     (Axiom V)
#   Phase 6  — Operator Channel verification   (§5.3)
#   Phase 7  — First Activation Protocol       (if FIRST_BOOT.md present)
#   Phase 8  — Drift probes                    (Axiom II)
#   Token    — Session token issued
#   Cycle    — Cognitive cycle
#   Token    — Session token revoked
#   Sleep    — Sleep Cycle (MIL consolidation)

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
source "$FCP_REF_ROOT/skills/lib/drift.sh"

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
TOKEN_FILE="$FCP_REF_ROOT/state/sentinels/session.token"
BASELINE_FILE="$FCP_REF_ROOT/state/baseline.json"
INTEGRITY_LOG="$FCP_REF_ROOT/state/integrity.log"
RECOVERY_FILE="$FCP_REF_ROOT/state/sentinels/recovery.attempts"
BEACON_FILE="$FCP_REF_ROOT/state/distress.beacon"

# Populated by load_baseline
N_BOOT=3
N_CHANNEL=3
N_RETRY=3
I_SECONDS=300
HEARTBEAT_T=10
CHANNEL_PATH="state/operator_notifications"

# Runtime
DRY_RUN=false
SKIP_DRIFT=false
CYCLE_COUNT=0
LAST_VITAL_CHECK=0

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
sil_log()       { echo "[SIL:$1] $2" >&2; }
baseline_get()  { python3 "$SIL_HELPERS" baseline-get "$1"; }

integrity_log() {
    local component="$1" event="$2" detail="${3:-}"
    local ts
    ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    printf '{"ts":"%s","component":"%s","event":"%s","detail":"%s"}\n' \
        "$ts" "$component" "$event" "$detail" >> "$INTEGRITY_LOG"
}

# ---------------------------------------------------------------------------
# Operator Channel  (HACA-Core §5.3)
# Mechanism: file — writes JSON to state/operator_notifications/.
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
# Readable from Entity Store without network or running processes.
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
# Phase 0 — Sandbox / Topology enforcement  (HACA-Core Axiom I)
# Transparent CPE topology required. Opaque → boot abort.
# ---------------------------------------------------------------------------
phase0_sandbox() {
    if [ "$$" -eq 1 ] || grep -qaE 'docker|lxc|containerd|libpod' /proc/1/cgroup 2>/dev/null; then
        sil_log "BOOT" "Confinement verified (container)."
        return 0
    fi
    if command -v unshare >/dev/null 2>&1; then
        sil_log "BOOT" "Re-executing inside private namespace..."
        exec unshare -m -p -f -r --mount-proc "$0" "$@"
    fi
    sil_log "FATAL" "Axiom I: Confinement Fault — unshare unavailable."
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
    I_SECONDS=$(baseline_get heartbeat.I_seconds)
    HEARTBEAT_T=$(baseline_get heartbeat.T)
    CHANNEL_PATH=$(baseline_get operator_channel.path)
    mkdir -p "$FCP_REF_ROOT/$CHANNEL_PATH"
    sil_log "BOOT" "Structural baseline loaded."
}

# ---------------------------------------------------------------------------
# Phase 2 — Integrity Document validation  (HACA-Core Axiom II)
# ---------------------------------------------------------------------------
phase2_integrity() {
    sil_log "BOOT" "Verifying Integrity Document..."
    if ! python3 "$SIL_HELPERS" verify-integrity; then
        integrity_log "sil" "INTEGRITY_MISMATCH" "boot"
        sil_log "FATAL" "Integrity mismatch — Axiom II Violation."
        exit 1
    fi
    integrity_log "sil" "INTEGRITY_OK" "boot"
}

# ---------------------------------------------------------------------------
# Phase 3 — Distress Beacon check
# Active beacon → suspended halt, no token issued.
# ---------------------------------------------------------------------------
phase3_beacon() {
    [ -f "$BEACON_FILE" ] || return 0
    sil_log "HALT" "Passive Distress Beacon is active."
    sil_log "HALT" "Resolve the condition, then: rm $BEACON_FILE"
    exit 1
}

# ---------------------------------------------------------------------------
# Phase 4 — Crash recovery  (HACA-Core §5.1)
# Stale token = crash indicator. Unresolved Action Ledger → Operator review.
# ---------------------------------------------------------------------------
phase4_crash_recovery() {
    local crash_count=0
    [ -f "$RECOVERY_FILE" ] && crash_count=$(cat "$RECOVERY_FILE" 2>/dev/null || echo 0)

    if [ ! -f "$TOKEN_FILE" ]; then
        echo "0" > "$RECOVERY_FILE"
        return 0
    fi

    sil_log "RECOVERY" "Stale session token — crash detected."
    integrity_log "sil" "CRASH_DETECTED" "stale_token"
    crash_count=$((crash_count + 1))
    echo "$crash_count" > "$RECOVERY_FILE"

    if [ "$crash_count" -ge "$N_BOOT" ]; then
        sil_log "FATAL" "Boot loop: $crash_count crashes (N_boot=$N_BOOT)."
        distress_beacon_activate "boot_loop_$crash_count"
        operator_notify_with_retry "CRITICAL" "sil" "Boot loop detected: $crash_count crashes. Beacon activated."
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
    operator_notify "CRITICAL" "sil" "Unresolved Action Ledger entries from crashed session."

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
# Phase 5 — Operator Bound verification  (HACA-Core Axiom V)
# No valid Bound → permanent inactivity, no token issued.
# ---------------------------------------------------------------------------
phase5_operator_bound() {
    if ! python3 "$SIL_HELPERS" verify-operator-bound; then
        sil_log "HALT" "Axiom V: No valid Operator Bound."
        sil_log "HALT" "Run First Activation Protocol to enroll an Operator."
        integrity_log "sil" "OPERATOR_BOUND_INVALID" "boot"
        exit 1
    fi
    sil_log "BOOT" "Operator Bound verified."
    integrity_log "sil" "OPERATOR_BOUND_OK" "boot"
}

# ---------------------------------------------------------------------------
# Phase 6 — Operator Channel verification  (HACA-Core §5.3)
# ---------------------------------------------------------------------------
phase6_operator_channel() {
    local channel_dir="$FCP_REF_ROOT/$CHANNEL_PATH"
    if ! mkdir -p "$channel_dir" 2>/dev/null; then
        sil_log "FATAL" "Operator Channel unavailable: $channel_dir"
        integrity_log "sil" "OPERATOR_CHANNEL_FAIL" "boot"
        exit 1
    fi
    sil_log "BOOT" "Operator Channel verified."
    integrity_log "sil" "OPERATOR_CHANNEL_OK" "boot"
}

# ---------------------------------------------------------------------------
# Phase 7 — First Activation Protocol  (HACA-Arch §6.2)
# ---------------------------------------------------------------------------
phase7_fap() {
    local fap_file="$FCP_REF_ROOT/FIRST_BOOT.md"
    [ -f "$fap_file" ] || return 0
    sil_log "BOOT" "FIRST_BOOT.md detected — First Activation Protocol will run."
    integrity_log "sil" "FAP_DETECTED" "first_boot"
    SKIP_DRIFT=true
    export FCP_FAP_MODE=true
    export FCP_FAP_FILE="$fap_file"
}

# ---------------------------------------------------------------------------
# Phase 8 — Drift probes  (HACA-Core Axiom II)
# Any drift → immediate Critical. No Degraded, no tolerance.
# ---------------------------------------------------------------------------
phase8_drift() {
    if [ "$SKIP_DRIFT" = "true" ]; then
        sil_log "BOOT" "Drift probes skipped (first boot)."
        return 0
    fi
    sil_log "BOOT" "Running drift probes..."
    if ! drift_run_probes --skip-oracle 2>/dev/null; then
        integrity_log "sil" "DRIFT_CRITICAL" "unauthorized_drift_at_boot"
        operator_notify_with_retry "CRITICAL" "sil" \
            "Axiom II Violation: Unauthorized Drift — session token withheld."
        sil_log "FATAL" "Axiom II: Unauthorized Drift → Critical."
        exit 1
    fi
    sil_log "BOOT" "Drift probes passed."
    integrity_log "sil" "DRIFT_OK" "boot"
}

# ---------------------------------------------------------------------------
# Session Token
# ---------------------------------------------------------------------------
issue_token() {
    local token
    token=$(acp_new_tx)
    echo "$token" > "$TOKEN_FILE"
    echo "0" > "$RECOVERY_FILE"
    sil_log "BOOT" "Session token issued: ${token:0:8}..."
    integrity_log "sil" "SESSION_OPEN" "token=${token:0:8}"
}

revoke_token() {
    rm -f "$TOKEN_FILE"
    sil_log "HALT" "Session token revoked."
    integrity_log "sil" "SESSION_CLOSE" "token_revoked"
}

# ---------------------------------------------------------------------------
# Heartbeat Vital Check  (HACA-Core §4.2)
# Identity Drift: persona hashes vs Integrity Document.
# Any mismatch → Critical, revoke token.
# ---------------------------------------------------------------------------
heartbeat_vital_check() {
    sil_log "SESSION" "Heartbeat Vital Check (cycle=$CYCLE_COUNT)..."
    if ! python3 "$SIL_HELPERS" check-persona-drift; then
        integrity_log "sil" "IDENTITY_DRIFT_CRITICAL" "cycle=$CYCLE_COUNT"
        revoke_token
        operator_notify_with_retry "CRITICAL" "sil" \
            "Axiom II: Identity Drift at Heartbeat — session terminated."
        sil_log "FATAL" "Axiom II: Identity Drift → Critical."
        exit 1
    fi
    LAST_VITAL_CHECK=$(date +%s)
    integrity_log "sil" "HEARTBEAT_OK" "cycle=$CYCLE_COUNT"
}

# ---------------------------------------------------------------------------
# Session Cycle  (HACA-Arch §6.3)
# Returns 1 to signal session-close (context window critical).
# ---------------------------------------------------------------------------
session_cycle() {
    sil_log "SESSION" "Cognitive cycle $((CYCLE_COUNT + 1))..."

    # CPE already signaled context window critical in previous cycle
    if [ "${FCP_CONTEXT_CRITICAL:-false}" = "true" ]; then
        sil_log "SESSION" "Context window critical — closing session."
        integrity_log "sil" "CONTEXT_WINDOW_CRITICAL" "session_close"
        operator_notify "INFO" "sil" "Context window critical — session closed for consolidation."
        return 1
    fi

    "$MIL" drain

    local context
    context=$("$CPE" context)

    if [ "$DRY_RUN" = "true" ]; then
        echo "$context"
        return 0
    fi

    local output
    output=$("$CPE" query <<< "$context")

    # Log CPE response
    local response_json
    response_json=$(python3 -c \
        "import json,sys; print(json.dumps({'role':'assistant','content':sys.argv[1]}))" \
        "$output")
    acp_write "supervisor" "MSG" "$response_json" >/dev/null

    # Parse and dispatch actions (SIL mediates all host actuation)
    local actions
    actions=$("$CPE" parse <<< "$output")

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
                # Outcome is never returned to CPE.
                integrity_log "sil" "EVOLUTION_PROPOSAL_RECEIVED" "pending_operator_review"
                operator_notify "INFO" "sil" "Evolution Proposal received — awaiting Operator approval."
                ;;
            session_close)
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
                [ -n "$atype" ] && sil_log "WARN" "Unknown action: $atype"
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
# Sleep Cycle  (HACA-Arch §6.4)
# ---------------------------------------------------------------------------
sleep_cycle() {
    sil_log "SLEEP" "Starting Sleep Cycle..."
    integrity_log "sil" "SLEEP_CYCLE_START" ""
    "$MIL" consolidate
    integrity_log "sil" "SLEEP_CYCLE_COMPLETE" ""
    sil_log "SLEEP" "Sleep Cycle complete."
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)    DRY_RUN=true;    shift ;;
        --skip-drift) SKIP_DRIFT=true; shift ;;
        *) shift ;;
    esac
done

LAST_VITAL_CHECK=$(date +%s)

phase0_sandbox "$@"
phase1_baseline
phase2_integrity
phase3_beacon
phase4_crash_recovery
phase5_operator_bound
phase6_operator_channel
phase7_fap
phase8_drift
issue_token

if ! session_cycle; then
    sil_log "SESSION" "Session closed early (context window)."
fi

revoke_token
sleep_cycle
integrity_log "sil" "BOOT_COMPLETE" ""
sil_log "BOOT" "Process complete."
