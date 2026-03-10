#!/bin/bash
# sil.sh — System Integrity Layer / Host Daemon (FCP §6)
#
# Implements the 7-phase boot sequence:
#   Phase 0: Host Introspection  → state/env.md
#   Phase 1: Crash Recovery      → complete interrupted rotations, repair JSONL
#   Phase 2: Integrity Validation → SHA-256 check of immutable files
#   Phase 3: RBAC Resolution     → load authorized skills from skills/index.json
#   Phase 4: Context Assembly    → build CPE input context
#   Phase 5: Drift Probes        → (stub; requires embedding backend)
#   Phase 6: Ignition            → invoke CPE, parse output, execute skill loop
#
# Usage:
#   ./sil.sh [--dry-run] [--skip-drift] [--cycle <n>]
#
# Environment:
#   FCP_REF_ROOT     — FCP entity root (auto-detected if unset)
#   ANTHROPIC_API_KEY — required for Claude backend
#   CONTEXT_BUDGET  — max chars for session tail (default: 60000)

set -euo pipefail

# ---------------------------------------------------------------------------
# Bootstrap: locate FCP_REF_ROOT
# ---------------------------------------------------------------------------
if [ -z "${FCP_REF_ROOT:-}" ]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    if [ -f "$SCRIPT_DIR/BOOT.md" ]; then
        export FCP_REF_ROOT="$SCRIPT_DIR"
    else
        echo "[SIL] FATAL: cannot locate FCP_REF_ROOT (no BOOT.md found)" >&2
        exit 1
    fi
fi
export FCP_REF_CONTEXT="${FCP_REF_CONTEXT:-$FCP_REF_ROOT}"

# Load libraries
source "$FCP_REF_ROOT/skills/lib/acp.sh"
source "$FCP_REF_ROOT/skills/lib/rotation.sh"
source "$FCP_REF_ROOT/skills/lib/drift.sh"

# ---------------------------------------------------------------------------
# Args
# ---------------------------------------------------------------------------
DRY_RUN=false
SKIP_DRIFT=false
CYCLE_OVERRIDE=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)      DRY_RUN=true;          shift ;;
        --skip-drift)   SKIP_DRIFT=true;        shift ;;
        --cycle)        CYCLE_OVERRIDE="$2";    shift 2 ;;
        *) echo "[SIL] Unknown argument: $1" >&2; exit 1 ;;
    esac
done

CONTEXT_BUDGET="${CONTEXT_BUDGET:-60000}"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
sil_log() {
    local level="$1"; shift
    echo "[SIL:${level}] $*" >&2
}

sil_abort() {
    sil_log "FATAL" "$*"
    # Write a TRAP envelope to inbox before dying
    acp_write "sil" "TRAP" \
        "{\"reason\":\"boot_abort\",\"message\":$(python3 -c "import json,sys; print(json.dumps(sys.argv[1]))" "$*")}" \
        || true
    exit 1
}

sil_acp_note() {
    local type="$1"
    local data="$2"
    acp_write "sil" "$type" "$data" >/dev/null
}

# ---------------------------------------------------------------------------
# PHASE 0 — Host Introspection
# ---------------------------------------------------------------------------
phase0_introspect() {
    sil_log "PHASE0" "Host introspection..."

    local env_file="$FCP_REF_ROOT/state/env.md"

    # --- Sandbox verification (FCP §10) ---
    local sandbox_ok=true

    # Attempt write outside workspaces/ — must fail
    if touch /tmp/__fcp_sandbox_probe__ 2>/dev/null; then
        rm -f /tmp/__fcp_sandbox_probe__
        sil_log "PHASE0" "WARN: write outside FCP root is possible (degraded mode)"
        sandbox_ok=false
    fi

    # Detect filesystem type
    local fs_type
    fs_type=$(stat -f -c "%T" "$FCP_REF_ROOT" 2>/dev/null \
              || python3 -c "import subprocess; r=subprocess.run(['df','--output=fstype','$FCP_REF_ROOT'],capture_output=True,text=True); lines=r.stdout.strip().split('\n'); print(lines[-1].strip() if len(lines)>1 else 'unknown')" 2>/dev/null \
              || echo "unknown")

    # Collect available binaries
    local binaries=""
    for b in python3 jq curl git sha256sum awk sed; do
        command -v "$b" >/dev/null 2>&1 && binaries="${binaries} ${b}"
    done

    # Sandbox re-verification (HACA-Core Axiom VII.d — every SANDBOX_REVERIFY_INTERVAL cycles)
    local cycle_file="$FCP_REF_ROOT/state/sentinels/sil.cycle"
    local current_cycle
    current_cycle=$(cat "$cycle_file" 2>/dev/null || echo 0)
    local reverify_interval="${SANDBOX_REVERIFY_INTERVAL:-100}"
    if [ "$current_cycle" -gt 0 ] && [ $(( current_cycle % reverify_interval )) -eq 0 ]; then
        sil_log "PHASE0" "Periodic sandbox re-verification (cycle ${current_cycle}, interval ${reverify_interval})..."
        local reverify_ok=true
        if touch /tmp/__fcp_reverify_probe__ 2>/dev/null; then
            rm -f /tmp/__fcp_reverify_probe__
            sil_log "PHASE0" "SANDBOX FAULT: write outside FCP root succeeded at cycle ${current_cycle}."
            acp_write "sil" "TRAP" \
                "{\"reason\":\"sandbox_fault\",\"cycle\":${current_cycle},\"message\":\"write outside FCP root succeeded during periodic re-verification\"}" \
                >/dev/null 2>/dev/null || true
            # Enter degraded read-only mode (HACA-Core Axiom VII — MUST signal Sandbox Fault)
            export SIL_READ_ONLY=true
            sil_log "PHASE0" "SANDBOX FAULT: entering read-only mode for this cycle."
            reverify_ok=false
        fi
        [ "$reverify_ok" = "true" ] && sil_log "PHASE0" "Periodic sandbox re-verification: OK."
    fi

    # Compute cycle number
    local cycle=0
    [ -f "$cycle_file" ] && cycle=$(cat "$cycle_file" 2>/dev/null || echo 0)
    if [ -n "$CYCLE_OVERRIDE" ]; then
        cycle="$CYCLE_OVERRIDE"
    else
        cycle=$((cycle + 1))
    fi
    echo "$cycle" > "$cycle_file"

    local ts
    ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

    cat > "$env_file" <<EOF
# FCP Environment Snapshot — generated at boot (Phase 0)
# DO NOT EDIT — this file is regenerated every boot

ts: ${ts}
cycle: ${cycle}
fcp_ref_root: ${FCP_REF_ROOT}
os: $(uname -srm)
user: $(whoami)
filesystem: ${fs_type}
context_budget: ${CONTEXT_BUDGET}
execution_mode: transparent
sandbox_verified: ${sandbox_ok}
binaries:${binaries}
EOF

    sil_log "PHASE0" "env.md written. cycle=${cycle}, fs=${fs_type}, sandbox=${sandbox_ok}"
    echo "$cycle"
}

# ---------------------------------------------------------------------------
# PHASE 1 — Crash Recovery
# ---------------------------------------------------------------------------
phase1_recover() {
    sil_log "PHASE1" "Crash recovery..."

    # Recovery attempt counter (HACA-Core Axiom V — max 3 consecutive attempts)
    local attempts_file="$FCP_REF_ROOT/state/sentinels/recovery.attempts"
    local attempts
    attempts=$(cat "$attempts_file" 2>/dev/null || echo 0)
    if [ "$attempts" -ge 3 ]; then
        sil_log "PHASE1" "FATAL: max recovery attempts (3) exceeded — MIL may be permanently corrupt."
        sil_log "PHASE1" "Manual intervention required. Remove ${attempts_file} after fixing."
        sil_abort "Max recovery attempts exceeded. Halting to prevent data loss."
    fi
    echo $((attempts + 1)) > "$attempts_file"
    sil_log "PHASE1" "Recovery attempt $((attempts + 1))/3."

    # Complete any interrupted log rotation
    rotation_recover

    # Repair truncated/incomplete JSONL lines in session.jsonl
    local session="$FCP_REF_ROOT/memory/session.jsonl"
    if [ -f "$session" ]; then
        local repaired
        export _SIL_SESSION_PATH="$session"
        repaired=$(python3 << 'PYEOF'
import sys, json, os

session_path = os.environ['_SIL_SESSION_PATH']
good_lines = []
bad_count  = 0

with open(session_path, 'r', errors='replace') as f:
    for line in f:
        line = line.rstrip('\n')
        if not line:
            continue
        try:
            json.loads(line)
            good_lines.append(line)
        except json.JSONDecodeError:
            bad_count += 1

if bad_count > 0:
    with open(session_path, 'w') as f:
        for l in good_lines:
            f.write(l + '\n')
    print(f"repaired:{bad_count}")
else:
    print("ok")
PYEOF
        )
        sil_log "PHASE1" "session.jsonl repair: ${repaired}"
    fi

    # Drain any leftover .tmp files from spool (crashed writes)
    find "$FCP_REF_ROOT/memory/spool" -name "*.tmp" -delete 2>/dev/null || true

    sil_log "PHASE1" "Recovery complete."
}

# ---------------------------------------------------------------------------
# PHASE 2 — Integrity Validation
# ---------------------------------------------------------------------------
phase2_integrity() {
    sil_log "PHASE2" "Integrity validation..."

    local integrity_file="$FCP_REF_ROOT/state/integrity.json"
    [ -f "$integrity_file" ] || sil_abort "integrity.json not found"

    # SIL Anchor Hardening (HACA-Arch §5.4.1)
    # If INTEGRITY_HASH env var is set by the operator, verify integrity.json itself
    # before trusting any hashes inside it. This prevents coordinated tampering
    # (host modifies both integrity.json and artifacts simultaneously).
    #
    # Usage: export INTEGRITY_HASH=<sha256 of state/integrity.json>
    # Generate: sha256sum state/integrity.json | awk '{print $1}'
    if [ -n "${INTEGRITY_HASH:-}" ]; then
        local actual_hash
        actual_hash=$(sha256sum "$integrity_file" | awk '{print $1}')
        if [ "$actual_hash" != "$INTEGRITY_HASH" ]; then
            sil_log "PHASE2" "ANCHOR FAIL: integrity.json hash mismatch."
            sil_log "PHASE2" "  expected (operator): ${INTEGRITY_HASH}"
            sil_log "PHASE2" "  actual:              ${actual_hash}"
            sil_abort "SIL anchor verification failed. Possible coordinated tampering."
        fi
        sil_log "PHASE2" "Anchor OK: integrity.json matches operator-provided hash."
    else
        sil_log "PHASE2" "WARN: INTEGRITY_HASH not set — SIL anchor hardening disabled (HACA-Arch §5.4.1)."
    fi

    local fail=false

    python3 << PYEOF || fail=true
import json, hashlib, sys, os

root   = os.environ.get('FCP_REF_ROOT', '')
ifile  = os.path.join(root, 'state', 'integrity.json')

with open(ifile) as f:
    manifest = json.load(f)

sigs = manifest.get('signatures', {})
failed = []

for rel_path, expected_hash in sigs.items():
    full_path = os.path.join(root, rel_path)
    if not os.path.isfile(full_path):
        print(f"[SIL:PHASE2] MISSING: {rel_path}", file=sys.stderr)
        failed.append(rel_path)
        continue
    with open(full_path, 'rb') as f:
        actual = hashlib.sha256(f.read()).hexdigest()
    if actual != expected_hash:
        print(f"[SIL:PHASE2] MISMATCH: {rel_path}", file=sys.stderr)
        print(f"  expected: {expected_hash}", file=sys.stderr)
        print(f"  actual:   {actual}", file=sys.stderr)
        failed.append(rel_path)
    else:
        print(f"[SIL:PHASE2] OK: {rel_path}", file=sys.stderr)

if failed:
    sys.exit(1)
PYEOF

    if [ "$fail" = "true" ]; then
        sil_abort "Integrity check FAILED. Boot aborted to protect identity."
    fi

    sil_log "PHASE2" "All integrity checks passed."
}

# ---------------------------------------------------------------------------
# PHASE 3 — RBAC Resolution
# ---------------------------------------------------------------------------
# Returns a space-separated list of authorized skill paths
phase3_rbac() {
    sil_log "PHASE3" "RBAC resolution..."

    local index="$FCP_REF_ROOT/skills/index.json"
    [ -f "$index" ] || sil_abort "skills/index.json not found"

    AUTHORIZED_SKILLS=$(python3 -c "
import json, sys, os

root  = os.environ.get('FCP_REF_ROOT', '')
index = json.load(open(os.path.join(root, 'skills', 'index.json')))

authorized = []
for skill in index.get('skills', []):
    if skill.get('authorized', False):
        path = os.path.join(root, skill['path'])
        if os.path.isdir(path):
            authorized.append(skill['name'] + ':' + path)
        else:
            print(f'[SIL:PHASE3] WARN: skill path not found: {path}', file=sys.stderr)

print(' '.join(authorized))
")

    sil_log "PHASE3" "Authorized skills: ${AUTHORIZED_SKILLS}"
    export AUTHORIZED_SKILLS
}

# ---------------------------------------------------------------------------
# PHASE 4 — Context Assembly
# ---------------------------------------------------------------------------
phase4_assemble_context() {
    sil_log "PHASE4" "Assembling CPE context..."

    local context=""

    # [FIRST_BOOT] — FAP injection (FCP §0b, §6a)
    # If FIRST_BOOT.md exists, the CPE must execute FAP before processing any user input.
    local first_boot_file="$FCP_REF_ROOT/FIRST_BOOT.md"
    if [ -f "$first_boot_file" ]; then
        sil_log "PHASE4" "FIRST_BOOT.md detected — injecting FAP into context."
        context+=$'\n--- [FIRST_BOOT] ---\n'
        context+=$(cat "$first_boot_file")
        context+=$'\n'
    fi

    # [PERSONA] — lexicographic order
    context+=$'\n--- [PERSONA] ---\n'
    for f in "$FCP_REF_ROOT/persona/"*.md; do
        [ -f "$f" ] || continue
        context+=$'\n### '"$(basename "$f")"$'\n'
        context+=$(cat "$f")
        context+=$'\n'
    done

    # [BOOT] — the instruction manual
    context+=$'\n--- [BOOT PROTOCOL] ---\n'
    context+=$(cat "$FCP_REF_ROOT/BOOT.md")
    context+=$'\n'

    # [ENV] — host environment snapshot
    context+=$'\n--- [ENV] ---\n'
    context+=$(cat "$FCP_REF_ROOT/state/env.md")
    context+=$'\n'

    # [SKILLS INDEX] — RBAC registry (roles and authorized skill list)
    context+=$'\n--- [SKILLS INDEX] ---\n'
    context+=$(cat "$FCP_REF_ROOT/skills/index.json")
    context+=$'\n'

    # [SKILL:name] — authorized skill manifests
    for skill_entry in $AUTHORIZED_SKILLS; do
        local skill_name="${skill_entry%%:*}"
        local skill_path="${skill_entry#*:}"
        local skill_md="${skill_path}/SKILL.md"
        local skill_manifest="${skill_path}/manifest.json"

        context+=$'\n--- [SKILL:'"${skill_name}"'] ---\n'
        if [ -f "$skill_md" ]; then
            context+=$(cat "$skill_md")
        fi
        if [ -f "$skill_manifest" ]; then
            context+=$'\n**Manifest:**\n```json\n'
            context+=$(cat "$skill_manifest")
            context+=$'\n```\n'
        fi
    done

    # [MEMORY] — active_context symlinks, sorted by filename (priority prefix)
    local active_ctx="$FCP_REF_ROOT/memory/active_context"
    if [ -d "$active_ctx" ] && [ -n "$(ls -A "$active_ctx" 2>/dev/null | grep -v '\.keep')" ]; then
        context+=$'\n--- [MEMORY] ---\n'
        for link in "$active_ctx"/*; do
            [ -f "$link" ] || [ -L "$link" ] || continue
            [[ "$(basename "$link")" == ".keep" ]] && continue
            context+=$'\n### '"$(basename "$link")"$'\n'
            context+=$(cat "$link" 2>/dev/null || echo "(unreadable)")
            context+=$'\n'
        done
    fi

    # [CONCEPTS] — semantic graph .link files from memory/concepts/ (FCP §7.1)
    local concepts_dir="$FCP_REF_ROOT/memory/concepts"
    if [ -d "$concepts_dir" ] && [ -n "$(ls -A "$concepts_dir" 2>/dev/null | grep '\.link$')" ]; then
        context+=$'\n--- [SEMANTIC GRAPH] ---\n'
        for link_file in "$concepts_dir"/*.link; do
            [ -f "$link_file" ] || continue
            [[ "$(basename "$link_file")" == README* ]] && continue
            local concept_name
            concept_name="$(basename "$link_file" .link)"
            context+=$'\n### concept:'"${concept_name}"$'\n'
            # Each non-comment line is a path to a memory fragment
            while IFS= read -r fragment_path; do
                [[ "$fragment_path" == \#* ]] && continue
                [ -z "$fragment_path" ] && continue
                local full_path="$FCP_REF_ROOT/$fragment_path"
                if [ -f "$full_path" ]; then
                    context+=$(cat "$full_path" 2>/dev/null || echo "(unreadable)")
                    context+=$'\n'
                fi
            done < "$link_file"
        done
    fi

    # [SESSION] — tail of session.jsonl, newest-first, respecting context budget
    local session="$FCP_REF_ROOT/memory/session.jsonl"
    if [ -f "$session" ] && [ -s "$session" ]; then
        context+=$'\n--- [SESSION] ---\n'
        local session_content
        session_content=$(python3 << PYEOF
import json, os, sys

session_path = os.path.join(os.environ['FCP_REF_ROOT'], 'memory', 'session.jsonl')
budget       = int(os.environ.get('CONTEXT_BUDGET', '60000'))
current_used = int(os.environ.get('_CTX_USED', '0'))
remaining    = max(0, budget - current_used)

lines = []
with open(session_path, 'r', errors='replace') as f:
    for line in f:
        line = line.rstrip('\n')
        if line:
            lines.append(line)

# Newest-first
lines.reverse()

out      = []
skipped  = 0
used     = 0

for line in lines:
    if used + len(line) + 1 > remaining:
        skipped += 1
        continue
    out.append(line)
    used += len(line) + 1

if skipped > 0:
    print(f'(CTX_SKIP: {skipped} older entries dropped — context budget exhausted)')

for l in out:
    print(l)
PYEOF
        )
        export _CTX_USED=$((${#context} + ${#session_content}))
        context+="$session_content"
        context+=$'\n'
    fi

    echo "$context"
}

# ---------------------------------------------------------------------------
# PHASE 5 — Drift Probes (Two-Tier Cascade: NCD → LLM Oracle)
# ---------------------------------------------------------------------------
phase5_drift() {
    local skip="${1:-false}"

    if [ "$skip" = "true" ]; then
        sil_log "PHASE5" "Drift probes skipped (--skip-drift)."
        return 0
    fi

    sil_log "PHASE5" "Initiating Two-Tier Cascade Drift Detection (Tier 1: NCD/gzip)..."

    # Determine oracle options
    local drift_opts=""
    if [ "$DRY_RUN" = "true" ]; then
        drift_opts="--skip-oracle"
        sil_log "PHASE5" "DRY RUN — Tier 2 Oracle disabled."
    elif ! { "$FCP_REF_ROOT/skills/llm_backends/claude_api.sh" --test 2>/dev/null || \
              "$FCP_REF_ROOT/skills/llm_backends/ollama.sh" --test 2>/dev/null || \
              "$FCP_REF_ROOT/skills/llm_backends/openai.sh" --test 2>/dev/null; }; then
        drift_opts="--skip-oracle"
        sil_log "PHASE5" "No LLM backend available — Tier 2 Oracle disabled."
    fi

    local result_line
    if result_line=$(drift_run_probes $drift_opts 2>&1 | tee /dev/stderr | tail -1); then
        sil_log "PHASE5" "Drift result: ${result_line}"
    else
        # DRIFT_FAULT
        sil_log "PHASE5" "DRIFT_FAULT detected: ${result_line}"

        # Inject DRIFT_FAULT Trap into inbox
        local fault_data
        fault_data=$(printf '{"reason":"drift_threshold_exceeded","result":"%s"}' "$result_line")
        acp_write "sil" "DRIFT_FAULT" "$fault_data" >/dev/null

        # Enter read-only mode: export flag for Phase 6
        export SIL_READ_ONLY=true
        sil_log "PHASE5" "Entering read-only mode. CPE will respond but no state changes permitted."
        return 0  # Don't abort — let CPE see the DRIFT_FAULT and respond to operator
    fi
}

# ---------------------------------------------------------------------------
# PHASE 6 — Ignition: CPE invocation + skill execution loop
# ---------------------------------------------------------------------------
phase6_ignite() {
    local context="$1"
    local cycle="$2"

    sil_log "PHASE6" "Ignition. Cognitive cycle #${cycle}."

    # Write heartbeat lockfile
    local pulse_file="$FCP_REF_ROOT/state/pulses/sil.alive"
    mkdir -p "$(dirname "$pulse_file")"
    date -u +"%Y-%m-%dT%H:%M:%SZ" > "$pulse_file"

    if [ "$DRY_RUN" = "true" ]; then
        sil_log "PHASE6" "DRY RUN: context assembled (${#context} chars). CPE not invoked."
        echo "$context"
        return 0
    fi

    # Drain inbox → session.jsonl before CPE runs
    drain_inbox

    # Dot command resolution — check if operator input is a .command alias
    # If so, execute directly without invoking the CPE
    local last_user_msg
    last_user_msg=$(python3 -c "
import json, sys
try:
    lines = open('$FCP_REF_ROOT/memory/session.jsonl').readlines()
    for line in reversed(lines):
        env = json.loads(line)
        if env.get('actor') == 'supervisor' and env.get('type') == 'MSG':
            data = json.loads(env.get('data', '{}'))
            print(data.get('content', data.get('text', '')))
            break
except Exception:
    pass
" 2>/dev/null)

    if resolve_dot_command "$last_user_msg"; then
        sil_log "PHASE6" "Dot command handled. CPE not invoked."
        drain_inbox
        return 0
    fi

    # Invoke CPE (LLM)
    sil_log "PHASE6" "Invoking CPE (${#context} chars context)..."
    local cpe_output
    cpe_output=$("$FCP_REF_ROOT/skills/llm_query.sh" "$context" 2>/dev/null)

    if [ -z "$cpe_output" ]; then
        sil_log "PHASE6" "WARN: CPE returned empty output."
        return 0
    fi

    # Boot confirmation: CPE must include [BOOT OK] marker (BOOT.md §8, RFC §13.9)
    if ! echo "$cpe_output" | grep -qF "[BOOT OK]"; then
        sil_log "PHASE6" "WARN: CPE output missing [BOOT OK] marker — context may not have been parsed correctly."
        acp_write "sil" "TRAP" '{"reason":"missing_boot_ok","message":"CPE did not emit [BOOT OK] — possible context parse failure"}' >/dev/null
    else
        sil_log "PHASE6" "Boot confirmation: [BOOT OK] received."
    fi

    sil_log "PHASE6" "CPE responded (${#cpe_output} chars). Writing to spool..."

    # Write CPE response to session via spool
    local response_data
    response_data=$(python3 -c "import json,sys; print(json.dumps({'role':'assistant','content':sys.argv[1]}))" "$cpe_output")
    acp_write "supervisor" "MSG" "$response_data" >/dev/null

    # Parse and execute actions from CPE output
    execute_actions "$cpe_output"

    # Drain inbox again after skill execution
    drain_inbox

    # Update heartbeat
    date -u +"%Y-%m-%dT%H:%M:%SZ" > "$pulse_file"

    sil_log "PHASE6" "Cognitive cycle #${cycle} complete."
}

# ---------------------------------------------------------------------------
# resolve_dot_command <user_message>
# If the message starts with a .command alias (from skills/index.json aliases),
# translates it into an fcp-actions skill_request and executes it directly,
# bypassing the CPE. Returns 0 if handled, 1 if not a dot command.
# ---------------------------------------------------------------------------
resolve_dot_command() {
    local msg="$1"
    local first_token
    first_token=$(echo "$msg" | awk '{print $1}')

    # Must start with '.' and have at least 2 chars
    [[ "$first_token" == .?* ]] || return 1

    local index="$FCP_REF_ROOT/skills/index.json"
    local skill_name
    skill_name=$(python3 -c "
import json, sys
idx = json.load(open('$index'))
aliases = idx.get('aliases', {})
cmd = sys.argv[1]
print(aliases.get(cmd, ''))
" "$first_token" 2>/dev/null)

    [ -z "$skill_name" ] && return 1

    sil_log "ALIAS" "Dot command '$first_token' → skill '$skill_name'"

    # Extract the argument (everything after the command token)
    local arg
    arg=$(echo "$msg" | sed "s|^${first_token}[[:space:]]*||")

    # Build a minimal skill_request and execute it
    local action_json
    action_json=$(python3 -c "
import json, sys
skill = sys.argv[1]
arg   = sys.argv[2]

# For skills that take a single content/reason/summary param,
# map the free-text arg to the first required string param.
manifest_path = '$FCP_REF_ROOT/skills/' + skill + '/manifest.json'
try:
    manifest = json.load(open(manifest_path))
    params_schema = manifest.get('params', {})
    # Find first required string param
    first_param = next(
        (k for k, v in params_schema.items()
         if v.get('required') and v.get('type') == 'string'),
        None
    )
except Exception:
    first_param = None

if first_param and arg:
    params = {first_param: arg}
elif arg:
    params = {'content': arg}
else:
    params = {}

print(json.dumps({'action': 'skill_request', 'skill': skill, 'params': params}))
" "$skill_name" "$arg" 2>/dev/null)

    [ -z "$action_json" ] && return 1

    execute_single_action "$action_json"
    return 0
}

# ---------------------------------------------------------------------------
# drain_inbox — consolidate inbox/*.msg → session.jsonl (SIL is sole writer)
# ---------------------------------------------------------------------------
drain_inbox() {
    local inbox="$FCP_REF_ROOT/memory/inbox"
    local session="$FCP_REF_ROOT/memory/session.jsonl"
    local agenda="$FCP_REF_ROOT/state/agenda.jsonl"

    local count_session=0
    local count_agenda=0

    # Process msgs in chronological order (filename = epoch_ns-gseq)
    for msg in "$inbox"/*.msg; do
        [ -f "$msg" ] || continue

        # Route SCHEDULE envelopes to agenda.jsonl; everything else to session.jsonl
        local env_type
        env_type=$(python3 -c "
import json, sys
try:
    print(json.loads(open(sys.argv[1]).read()).get('type',''))
except:
    print('')
" "$msg" 2>/dev/null)

        if [ "$env_type" = "SCHEDULE" ]; then
            cat "$msg" >> "$agenda"
            count_agenda=$((count_agenda + 1))
        else
            cat "$msg" >> "$session"
            count_session=$((count_session + 1))
        fi
        rm -f "$msg"
    done

    [ "$count_session" -gt 0 ] && sil_log "DRAIN" "session: ${count_session} msgs → session.jsonl"
    [ "$count_agenda" -gt 0 ]  && sil_log "DRAIN" "agenda:  ${count_agenda} msgs → agenda.jsonl"

    # Check if rotation is needed
    rotation_maybe
}

# ---------------------------------------------------------------------------
# execute_actions — parse fcp-actions block from CPE output and execute skills
# ---------------------------------------------------------------------------
execute_actions() {
    local cpe_output="$1"

    # Extract the fcp-actions block
    local actions_json
    actions_json=$(python3 << 'PYEOF'
import sys, re, json

text = sys.stdin.read()

# Find fenced block tagged fcp-actions
pattern = r'```fcp-actions\n(.*?)```'
match = re.search(pattern, text, re.DOTALL)
if not match:
    sys.exit(0)

block = match.group(1).strip()
for line in block.splitlines():
    line = line.strip()
    if not line:
        continue
    try:
        obj = json.loads(line)
        print(json.dumps(obj))
    except json.JSONDecodeError as e:
        print(f'[SIL:ACTIONS] WARN: invalid action JSON: {line}', file=sys.stderr)
PYEOF
    <<< "$cpe_output")

    [ -z "$actions_json" ] && return 0

    sil_log "ACTIONS" "Parsing CPE actions..."

    while IFS= read -r action_line; do
        [ -z "$action_line" ] && continue
        execute_single_action "$action_line"
    done <<< "$actions_json"
}

execute_single_action() {
    local action_json="$1"

    local action_type
    action_type=$(python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('action',''))" "$action_json")

    case "$action_type" in
        skill_request)
            # In read-only mode (DRIFT_FAULT), skill_request actions are blocked
            if [ "${SIL_READ_ONLY:-false}" = "true" ]; then
                sil_log "ACTIONS" "READ-ONLY MODE: skill_request blocked (DRIFT_FAULT active)"
                acp_write "sil" "TRAP" \
                    '{"reason":"read_only_mode","message":"skill_request blocked — DRIFT_FAULT active"}' >/dev/null
                return 0
            fi

            local skill_name
            skill_name=$(python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('skill',''))" "$action_json")
            local params_json
            params_json=$(python3 -c "import json,sys; print(json.dumps(json.loads(sys.argv[1]).get('params',{})))" "$action_json")

            # Validate skill is authorized
            local skill_path=""
            for entry in $AUTHORIZED_SKILLS; do
                if [ "${entry%%:*}" = "$skill_name" ]; then
                    skill_path="${entry#*:}"
                    break
                fi
            done

            if [ -z "$skill_path" ]; then
                sil_log "ACTIONS" "REJECTED: skill '${skill_name}' not authorized"
                acp_write "sil" "SKILL_ERROR" \
                    "{\"skill\":\"${skill_name}\",\"reason\":\"not_authorized\"}" >/dev/null
                return 0
            fi

            sil_log "ACTIONS" "Executing skill: ${skill_name}"
            local skill_script="${skill_path}/${skill_name}.sh"
            [ -f "$skill_script" ] || skill_script=$(find "$skill_path" -name "*.sh" | head -1)

            if [ ! -f "$skill_script" ]; then
                sil_log "ACTIONS" "ERROR: no executable found in ${skill_path}"
                return 0
            fi

            # Export each param as SKILL_PARAM_<KEY> env var (uppercase).
            local _exported_vars
            _exported_vars=$(python3 -c "
import json, sys
params = json.loads(sys.argv[1])
for k, v in params.items():
    key = ''.join(c if c.isalnum() else '_' for c in k).upper()
    print(f'export SKILL_PARAM_{key}={json.dumps(str(v))}')
" "$params_json" 2>/dev/null)
            eval "$_exported_vars" 2>/dev/null || true

            # Execute with timeout (SKILL_TIMEOUT — RFC §4, BOOT.md)
            # Configurable via SKILL_EXEC_TIMEOUT env var (default: 60s)
            local exec_timeout="${SKILL_EXEC_TIMEOUT:-60}"
            local result exit_code=0
            result=$(timeout "$exec_timeout" bash "$skill_script" "$params_json" 2>&1) || exit_code=$?

            if [ "$exit_code" -eq 124 ]; then
                # timeout(1) returns 124 on expiry
                sil_log "ACTIONS" "Skill '${skill_name}' TIMEOUT (${exec_timeout}s)"
                local timeout_data
                timeout_data=$(python3 -c "import json,sys; print(json.dumps({'skill':sys.argv[1],'timeout_s':int(sys.argv[2])}))" \
                               "$skill_name" "$exec_timeout")
                acp_write "sil" "SKILL_TIMEOUT" "$timeout_data" >/dev/null
            elif [ "$exit_code" -ne 0 ]; then
                sil_log "ACTIONS" "Skill '${skill_name}' FAILED (exit ${exit_code}): ${result}"
                local err_data
                err_data=$(python3 -c "import json,sys; print(json.dumps({'skill':sys.argv[1],'error':sys.argv[2],'exit_code':int(sys.argv[3])}))" \
                           "$skill_name" "$result" "$exit_code")
                acp_write "sil" "SKILL_ERROR" "$err_data" >/dev/null
            else
                sil_log "ACTIONS" "Skill '${skill_name}' OK"
                local result_data
                result_data=$(python3 -c "import json,sys; print(json.dumps({'skill':sys.argv[1],'output':sys.argv[2]}))" \
                              "$skill_name" "$result")
                acp_write "sil" "SKILL_RESULT" "$result_data" >/dev/null
            fi
            ;;

        memory_flag)
            local op name target priority
            op=$(python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('op',''))" "$action_json")
            name=$(python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('name',''))" "$action_json")
            local active_ctx="$FCP_REF_ROOT/memory/active_context"

            case "$op" in
                add)
                    target=$(python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('target',''))" "$action_json")
                    priority=$(python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('priority','50'))" "$action_json")
                    ln -sf "$target" "${active_ctx}/${priority}-${name}" \
                        && sil_log "ACTIONS" "memory_flag add: ${priority}-${name} → ${target}"
                    ;;
                remove)
                    rm -f "${active_ctx}/"*"-${name}" \
                        && sil_log "ACTIONS" "memory_flag remove: ${name}"
                    ;;
                *)
                    sil_log "ACTIONS" "WARN: unknown memory_flag op: ${op}"
                    ;;
            esac
            ;;

        agenda_add)
            local cron task
            cron=$(python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('cron',''))" "$action_json")
            task=$(python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('task',''))" "$action_json")
            local agenda_data
            agenda_data=$(python3 -c "import json,sys; print(json.dumps({'cron':sys.argv[1],'task':sys.argv[2]}))" "$cron" "$task")
            acp_write "supervisor" "SCHEDULE" "$agenda_data" >/dev/null
            sil_log "ACTIONS" "agenda_add: cron='${cron}' task='${task}'"
            ;;

        log_note)
            local note
            note=$(python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('content',''))" "$action_json")
            acp_write "supervisor" "MSG" \
                "$(python3 -c "import json,sys; print(json.dumps({'role':'note','content':sys.argv[1]}))" "$note")" >/dev/null
            sil_log "ACTIONS" "log_note recorded."
            ;;

        reply)
            # CPE emits a reply to the operator (stdout in Transparent Mode)
            local content
            content=$(python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('content',''))" "$action_json")
            acp_write "supervisor" "MSG" \
                "$(python3 -c "import json,sys; print(json.dumps({'role':'reply','content':sys.argv[1]}))" "$content")" >/dev/null
            sil_log "ACTIONS" "reply: ${#content} chars"
            ;;

        trap)
            # CPE signals a system anomaly directly (bidirectional TRAP per RFC §4)
            local reason message
            reason=$(python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('reason','cpe_trap'))" "$action_json")
            message=$(python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('message',''))" "$action_json")
            local trap_data
            trap_data=$(python3 -c "import json,sys; print(json.dumps({'source':'cpe','reason':sys.argv[1],'message':sys.argv[2]}))" \
                        "$reason" "$message")
            acp_write "sil" "TRAP" "$trap_data" >/dev/null
            sil_log "ACTIONS" "TRAP from CPE: reason=${reason} — ${message}"
            ;;

        *)
            sil_log "ACTIONS" "WARN: unknown action type '${action_type}'"
            ;;
    esac
}

# ---------------------------------------------------------------------------
# PRE-PHASE 0 — Confinement Enforcement (HACA Axiom II)
# ---------------------------------------------------------------------------
# Transparently auto-sandboxes the SIL using Linux namespaces (unshare) if
# running in an unconfined host environment. Zero deployment friction: the
# operator simply runs ./sil.sh and isolation is established automatically.
#
# Detection: checks whether PID 1 is already namespace-isolated (container)
# or if we are PID 1 ourselves (already inside a namespace).
# Remediation: re-execs the entire boot sequence inside a private PID, mount,
# and user namespace via `unshare` (util-linux, present on all Linux distros).
# Abort: if unshare is unavailable and host is unconfined, Axiom II is violated.
verify_and_enforce_sandbox() {
    # Already inside a container or a private namespace (PID 1 = us or systemd-nspawn/docker)
    if [ "$$" -eq 1 ] || grep -qaE 'docker|lxc|containerd|libpod' /proc/1/cgroup 2>/dev/null; then
        sil_log "PREBOOT" "Sandbox verified (confined environment detected)."
        return 0
    fi

    sil_log "PREBOOT" "WARN: Unconfined execution detected. Initiating transparent auto-sandboxing..."

    if command -v unshare >/dev/null 2>&1; then
        sil_log "PREBOOT" "Re-executing inside private namespace (unshare -m -p -f -r --mount-proc)..."
        # unshare flags:
        #   -m  private mount namespace (host mounts invisible)
        #   -p  private PID namespace
        #   -f  fork before exec (required for -p)
        #   -r  map current UID to root inside namespace (rootless container)
        #   --mount-proc  remount /proc for the new PID namespace
        exec unshare -m -p -f -r --mount-proc "$0" "$@"
        # exec never returns on success
    fi

    sil_abort "Confinement Fault: unshare unavailable and host is unconfined. HACA Axiom II violated."
}

# ---------------------------------------------------------------------------
# MAIN — Boot Sequence
# ---------------------------------------------------------------------------
sil_log "BOOT" "===== FCP-Ref SIL boot sequence starting ====="
sil_log "BOOT" "FCP_REF_ROOT=${FCP_REF_ROOT}"

verify_and_enforce_sandbox "$@"
CYCLE=$(phase0_introspect)
phase1_recover
phase2_integrity

# Probe pool rotation (HACA-Core §4.8) — every PROBE_ROTATE_DAYS days (default: 30)
# Rotates active probe set from pool, then recalibrates embeddings and updates integrity hash.
_probe_rotate_interval="${PROBE_ROTATE_DAYS:-30}"
_probe_last_file="$FCP_REF_ROOT/state/sentinels/probe_last_rotated"
_probe_last=$(cat "$_probe_last_file" 2>/dev/null || echo 0)
_now=$(date +%s)
_days_since=$(( (_now - _probe_last) / 86400 ))
if [ "$_days_since" -ge "$_probe_rotate_interval" ] && [ -f "$FCP_REF_ROOT/state/drift-pool.jsonl" ]; then
    sil_log "BOOT" "Probe pool rotation due (${_days_since}d since last rotation, interval=${_probe_rotate_interval}d)."
    if bash "$FCP_REF_ROOT/tools/rotate_probes.sh" 2>/dev/null \
       && bash "$FCP_REF_ROOT/tools/calibrate_probes.sh" 2>/dev/null; then
        # Update integrity hash for new active set
        _new_hash=$(sha256sum "$FCP_REF_ROOT/state/drift-probes.jsonl" | awk '{print $1}')
        python3 -c "
import json
path = '${FCP_REF_ROOT}/state/integrity.json'
with open(path) as f: d = json.load(f)
d['signatures']['state/drift-probes.jsonl'] = '${_new_hash}'
with open(path, 'w') as f: json.dump(d, f, indent=2); f.write('\n')
" 2>/dev/null
        echo "$_now" > "$_probe_last_file"
        sil_log "BOOT" "Probe pool rotated. integrity.json updated."
    else
        sil_log "BOOT" "WARN: probe rotation failed — continuing with existing probe set."
    fi
fi

phase3_rbac
CONTEXT=$(phase4_assemble_context)
phase5_drift "$SKIP_DRIFT"
phase6_ignite "$CONTEXT" "$CYCLE"

# Clear recovery attempt counter on successful boot (HACA-Core Axiom V)
rm -f "$FCP_REF_ROOT/state/sentinels/recovery.attempts"

sil_log "BOOT" "===== Boot sequence complete (cycle #${CYCLE}) ====="
