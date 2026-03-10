#!/bin/bash
# skills/lib/drift.sh — Drift Detection Engine (FCP §9)
#
# Implements the 3-step behavioral drift detection process:
#   1. Submit probe prompt to CPE.
#   2. Compare actual vs expected using Unigram NCD.
#   3. Compute average score across the probe set.

source "$FCP_REF_ROOT/skills/lib/acp.sh"

# ---------------------------------------------------------------------------
# extract_unigrams <text or file>
# ---------------------------------------------------------------------------
extract_unigrams() {
    local input="$1"
    if [ -f "$input" ]; then
        tr '[:upper:]' '[:lower:]' < "$input"
    else
        echo "$input" | tr '[:upper:]' '[:lower:]'
    fi | sed -e 's/[^a-z0-9]/\n/g' | grep -v '^$' | sort -u
}

# ---------------------------------------------------------------------------
# calculate_ncd <expected_text> <actual_text>
# ---------------------------------------------------------------------------
calculate_ncd() {
    local expected="$1"
    local actual="$2"

    local uni_x="/tmp/ncd_x_$$"
    local uni_y="/tmp/ncd_y_$$"
    local uni_xy="/tmp/ncd_xy_$$"
    trap 'rm -f "$uni_x" "$uni_y" "$uni_xy"' RETURN

    extract_unigrams "$expected" > "$uni_x"
    extract_unigrams "$actual" > "$uni_y"
    sort -u "$uni_x" "$uni_y" > "$uni_xy"

    local c_x c_y c_xy min_c max_c
    c_x=$(gzip -c "$uni_x" | wc -c)
    c_y=$(gzip -c "$uni_y" | wc -c)
    c_xy=$(gzip -c "$uni_xy" | wc -c)

    min_c=$c_x; max_c=$c_y
    if [ "$c_y" -lt "$c_x" ]; then min_c=$c_y; max_c=$c_x; fi

    awk -v cxy="$c_xy" -v min="$min_c" -v max="$max_c" \
        'BEGIN { if (max==0) { print "0.0000" } else { printf "%.4f\n", (cxy - min) / max } }'
}

# ---------------------------------------------------------------------------
# drift_run_probes [--skip-oracle]
# ---------------------------------------------------------------------------
drift_run_probes() {
    local skip="${1:-false}"
    if [ "$skip" = "true" ]; then
        echo "score=0.0 status=SKIP"
        return 0
    fi

    local probes_file="$FCP_REF_ROOT/state/drift-probes.jsonl"
    local config_file="$FCP_REF_ROOT/state/drift-config.json"
    local llm_script="$FCP_REF_ROOT/skills/llm_query.sh"

    [ -f "$probes_file" ] || { echo "score=0.0 status=ERROR (probes file missing)"; return 0; }
    
    local threshold
    threshold=$(jq -r '.threshold // 0.15' "$config_file" 2>/dev/null || echo "0.15")

    echo "[SIL:PHASE5] Running drift probes (threshold ${threshold})..." >&2

    local total_score=0
    local count=0
    local failed=false

    # We use a temp file to store results since we're in a loop and subshells might lose variables
    local results_tmp="/tmp/drift_results_$$"
    touch "$results_tmp"
    trap 'rm -f "$results_tmp"' EXIT

    while read -r line; do
        [ -z "$line" ] && continue
        local probe_data
        probe_data=$(echo "$line" | jq -r '.data')
        local id=$(echo "$probe_data" | jq -r '.id')
        local prompt=$(echo "$probe_data" | jq -r '.prompt')
        local expected_text=$(echo "$probe_data" | jq -r '.expected_text')

        echo "[SIL:PHASE5] Querying probe $id..." >&2
        
        # 1. Submit to CPE (temperature=0 implied by deterministic backends like Ollama/Claude if configured)
        # Note: llm_query.sh should handle the temperature param if available
        local actual_response
        actual_response=$("$llm_script" "$prompt" 2>/dev/null || echo "")

        if [ -z "$actual_response" ]; then
            echo "[SIL:PHASE5] ERROR: Empty response for probe $id" >&2
            continue
        fi

        # 2. Compare actual vs expected using Unigram NCD
        local score
        score=$(calculate_ncd "$expected_text" "$actual_response")
        echo "[SIL:PHASE5] Probe $id NCD: $score" >&2
        
        echo "$score" >> "$results_tmp"
        count=$((count + 1))
    done < "$probes_file"

    if [ "$count" -eq 0 ]; then
        echo "score=0.0 status=ERROR (no probes executed)"
        return 0
    fi

    # 3. Compute average score
    local avg_score
    avg_score=$(awk '{sum+=$1} END { printf "%.4f\n", sum/NR }' "$results_tmp")

    local is_drifted
    is_drifted=$(awk -v s="$avg_score" -v t="$threshold" 'BEGIN { print (s > t) ? 1 : 0 }')

    if [ "$is_drifted" -eq 1 ]; then
        echo "[SIL:PHASE5] DRIFT_FAULT: average score $avg_score > threshold $threshold" >&2
        echo "score=${avg_score} threshold=${threshold} status=DRIFT_FAULT"
        return 1
    else
        echo "[SIL:PHASE5] DRIFT PASS: average score $avg_score" >&2
        echo "score=${avg_score} threshold=${threshold} status=PASS"
        return 0
    fi
}
