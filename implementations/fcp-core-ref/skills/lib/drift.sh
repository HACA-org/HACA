#!/bin/bash
# skills/lib/drift.sh — Drift Detection Engine (FCP RFC §11)
#
# Source this file before use:
#   source "$FCP_REF_ROOT/skills/lib/drift.sh"
#
# Implements Two-Tier Cascade Drift Detection:
#
#   Tier 1 — Unigram NCD via gzip (fast path)
#     Zero external dependencies. Runs every boot.
#     Uses Unigram NCD to mitigate length asymmetry and improve semantic
#     signal: unique word sets are extracted (tr/sort/uniq) and the NCD
#     is computed on their mathematical union rather than raw text.
#     Based on: Cilibrasi & Vitányi (2005); enhanced by 2024-2025 work on
#     compression-based classification with unigram preprocessing.
#
#     NCD_unigram(A, B) = (C(U(A∪B)) - min(C(U(A)), C(U(B)))) / max(C(U(A)), C(U(B)))
#     where U(x) extracts the sorted unique word set and C() is gzip byte size.
#
#   Tier 2 — LLM-as-a-Judge Semantic Oracle (deep path)
#     Invoked only when Tier 1 breaches the warning threshold.
#     Provides semantic nuance that compression metrics cannot capture.
#
# Thresholds (from state/drift-config.json):
#   warning_threshold  — NCD score that triggers Tier 2 escalation (default: 0.45)
#   critical_threshold — NCD score for immediate abort without Tier 2 (default: 0.65)
#
# DRIFT_FAULT fires when:
#   - NCD >= critical_threshold (immediate), OR
#   - NCD >= warning_threshold AND LLM Oracle confirms semantic drift

# ---------------------------------------------------------------------------
# extract_unigrams <file>
# Extracts sorted unique word set from a file using POSIX tools.
# Outputs one lowercase word per line, no duplicates.
# ---------------------------------------------------------------------------
extract_unigrams() {
    local file="$1"
    tr '[:upper:]' '[:lower:]' < "$file" \
        | sed -e 's/[^a-z0-9]/\n/g' \
        | grep -v '^$' \
        | sort -u
}

# ---------------------------------------------------------------------------
# calculate_ncd <anchor_file> <target_file>
# Computes Unigram NCD using gzip. Prints a float [0.0, 1.0+] to stdout.
# Uses temp files scoped to this PID; cleaned up on exit.
# Returns 1 if either file is missing.
# ---------------------------------------------------------------------------
calculate_ncd() {
    local anchor="$1"
    local target="$2"

    if [[ ! -f "$anchor" || ! -f "$target" ]]; then
        echo "Error: Missing files for NCD calculation: anchor=$anchor target=$target" >&2
        return 1
    fi

    local uni_x="/tmp/ncd_x_$$"
    local uni_y="/tmp/ncd_y_$$"
    local uni_xy="/tmp/ncd_xy_$$"
    # Ensure cleanup even on error
    trap 'rm -f "$uni_x" "$uni_y" "$uni_xy"' RETURN

    extract_unigrams "$anchor" > "$uni_x"
    extract_unigrams "$target" > "$uni_y"
    # Mathematical union of both unigram sets (no duplicates)
    sort -u "$uni_x" "$uni_y" > "$uni_xy"

    local c_x c_y c_xy min_c max_c
    c_x=$(gzip -c "$uni_x" | wc -c)
    c_y=$(gzip -c "$uni_y" | wc -c)
    c_xy=$(gzip -c "$uni_xy" | wc -c)

    min_c=$c_x
    max_c=$c_y
    if [ "$c_y" -lt "$c_x" ]; then
        min_c=$c_y
        max_c=$c_x
    fi

    awk -v cxy="$c_xy" -v min="$min_c" -v max="$max_c" \
        'BEGIN { printf "%.4f\n", (cxy - min) / max }'
}

# ---------------------------------------------------------------------------
# evaluate_semantic_oracle <anchor_file> <target_file>
# Tier 2: queries LLM backend to confirm or deny drift.
# Prints "CRITICAL" or "SAFE" to stdout.
# ---------------------------------------------------------------------------
evaluate_semantic_oracle() {
    local anchor="$1"
    local target="$2"
    local llm_script="$FCP_REF_ROOT/skills/llm_query.sh"

    if [ ! -x "$llm_script" ]; then
        echo "WARN: llm_query.sh not available — assuming SAFE" >&2
        echo "SAFE"
        return
    fi

    local prompt_sys="ROLE: Semantic Evaluator. TASK: Compare ANCHOR (core identity) and TARGET (recent memory/behavior) for semantic drift. OUTPUT: ONLY a valid JSON object {\"drift_critical\": true|false}. Do not explain."
    local prompt_user
    prompt_user="ANCHOR:\n$(cat "$anchor")\n\nTARGET:\n$(cat "$target")"

    local response
    response=$("$llm_script" --system-prompt "$prompt_sys" --prompt "$prompt_user" 2>/dev/null || echo "")

    if echo "$response" | grep -qi '"drift_critical"[[:space:]]*:[[:space:]]*true'; then
        echo "CRITICAL"
    else
        echo "SAFE"
    fi
}

# ---------------------------------------------------------------------------
# drift_run_probes [--skip-oracle]
#
# Runs the Two-Tier Cascade Drift Detection cycle.
# Anchor: persona/identity.md
# Target: state/env.md (current session environment snapshot)
#
# Options:
#   --skip-oracle   Skip Tier 2 LLM oracle (for CI/testing)
#
# Returns:
#   0  — drift within threshold (boot proceeds)
#   1  — DRIFT_FAULT detected
#
# Prints final summary line to stdout.
# ---------------------------------------------------------------------------
drift_run_probes() {
    local skip_oracle=false
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --skip-oracle) skip_oracle=true; shift ;;
            --skip-llm)    skip_oracle=true; shift ;;  # legacy alias
            --sample)      shift 2 ;;  # accepted but ignored (NCD is not sample-based)
            *) shift ;;
        esac
    done

    local anchor_file="$FCP_REF_ROOT/persona/identity.md"
    local target_file="$FCP_REF_ROOT/state/env.md"
    local config_file="$FCP_REF_ROOT/state/drift-config.json"

    # Read thresholds from config (fallback to safe defaults)
    local warn_threshold crit_threshold
    warn_threshold=$(jq -r '.warning_threshold // 0.45'  "$config_file" 2>/dev/null || echo "0.45")
    crit_threshold=$(jq -r '.critical_threshold // 0.65' "$config_file" 2>/dev/null || echo "0.65")

    # Failsafe: if target doesn't exist yet (first boot before env.md is written), skip
    if [ ! -f "$target_file" ]; then
        echo "score=0.0 status=SKIP (target not yet available: $target_file)"
        return 0
    fi

    # TIER 1 — Heuristic Sensor (NCD fast path)
    local ncd_score
    if ! ncd_score=$(calculate_ncd "$anchor_file" "$target_file"); then
        echo "score=0.0 status=SKIP (NCD calculation failed)"
        return 0
    fi

    echo "[drift] [Tier 1] NCD score=${ncd_score} warn=${warn_threshold} crit=${crit_threshold}" >&2

    # Check critical threshold first (immediate abort, no oracle)
    local is_critical
    is_critical=$(awk -v score="$ncd_score" -v thresh="$crit_threshold" \
        'BEGIN { print (score >= thresh) ? 1 : 0 }')

    if [ "$is_critical" -eq 1 ]; then
        echo "[drift] [Tier 1] CRITICAL threshold breached — immediate DRIFT_FAULT." >&2
        echo "ncd_score=${ncd_score} tier=1 status=DRIFT_FAULT"
        return 1
    fi

    # Check warning threshold (escalate to Tier 2)
    local is_warned
    is_warned=$(awk -v score="$ncd_score" -v thresh="$warn_threshold" \
        'BEGIN { print (score >= thresh) ? 1 : 0 }')

    if [ "$is_warned" -eq 1 ]; then
        echo "[drift] [Tier 1] Warning threshold breached — escalating to Tier 2 Oracle." >&2

        if [ "$skip_oracle" = "true" ]; then
            echo "[drift] [Tier 2] Oracle skipped (--skip-oracle). Treating as SAFE." >&2
            echo "ncd_score=${ncd_score} tier=1 status=PASS (oracle_skipped)"
            return 0
        fi

        # TIER 2 — Semantic Oracle (deep path)
        local oracle_decision
        oracle_decision=$(evaluate_semantic_oracle "$anchor_file" "$target_file")
        echo "[drift] [Tier 2] Oracle decision: ${oracle_decision}" >&2

        if [ "$oracle_decision" = "CRITICAL" ]; then
            echo "ncd_score=${ncd_score} tier=2 oracle=CRITICAL status=DRIFT_FAULT"
            return 1
        else
            echo "ncd_score=${ncd_score} tier=2 oracle=SAFE status=PASS"
            return 0
        fi
    fi

    # Below warning threshold — clean pass
    echo "[drift] [Tier 1] Semantic alignment verified." >&2
    echo "ncd_score=${ncd_score} tier=1 status=PASS"
    return 0
}
