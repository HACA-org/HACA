#!/bin/bash
# skills/lib/drift.sh — Drift Detection Engine (FCP §9)
#
# Two-layer Semantic Probe execution against Memory Store content.
# No LLM invocation. Delegates to core/sil_helpers.py.
#
# Layer 1 — Deterministic: keyword / forbidden-pattern checks.
# Layer 2 — Probabilistic: gzip-NCD comparison with reference text.
#
# Public interface:
#   drift_run_probes [--skip-llm|--skip-oracle]
#     Runs scan-memory-drift via sil_helpers.py.
#     Exits 0 on pass, 1 on drift.
#     --skip-llm / --skip-oracle accepted for compatibility (no-ops).

SIL_HELPERS="${SIL_HELPERS:-$FCP_REF_ROOT/core/sil_helpers.py}"

drift_run_probes() {
    # Accept legacy flags for compatibility; no LLM is invoked.
    while [[ $# -gt 0 ]]; do
        shift
    done
    python3 "$SIL_HELPERS" scan-memory-drift
}
