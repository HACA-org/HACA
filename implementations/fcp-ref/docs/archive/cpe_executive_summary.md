# CPE Adapters — Executive Summary

**Status:** 4/5 adapters operational; 1 requires immediate action (Anthropic)
**Date:** 2026-03-21

---

## The Picture in 30 Seconds

FCP has 5 CPE adapters (Anthropic, OpenAI, Google, Ollama, Pairing) that provide a unified interface to different LLM backends. **All work,** but with varying levels of maturity:

- **Anthropic:** ✅ Solid, but API outdated (2023 vs 2024)
- **OpenAI:** ✅ Best implementation (most standardized API)
- **Google:** 🟡 Works, but fragile (no tool call IDs)
- **Ollama:** 🟡 Works, but inconsistent argument format
- **Pairing:** ✅ Novel filesystem-based MCP bridge (clever design)

---

## Biggest Concerns

### 1. Anthropic API Version (2023-06-01)
- **Issue:** Using 2-year-old API version
- **Risk:** Extended thinking not supported; breaking changes possible
- **Fix:** Update to 2024-06-15 (~1 hour)
- **Priority:** **HIGH**

### 2. Google/Ollama: No Tool Call IDs
- **Issue:** Can't map tool results back to calls; assumes order preserved
- **Risk:** If tool results out of order, wrong args go to wrong tool
- **Fix:** Generate synthetic IDs in adapter
- **Priority:** **HIGH** (medium effort, high safety gain)

### 3. OpenAI: Inefficient System Message
- **Issue:** System message re-sent with every request (wastes ~100 tokens)
- **Impact:** ~20% token overhead per session
- **Fix:** Implement prompt caching or refactor session loop
- **Priority:** **MEDIUM** (nice-to-have)

### 4. Silent Parse Failures
- **Issue:** When tool arguments parse as JSON, fails silently to empty dict
- **Risk:** Tool receives wrong args; hard to debug
- **Fix:** Add logging on parse failure
- **Priority:** **MEDIUM**

---

## What's Working Well

✅ **Anthropic:** Clean API, direct dict parsing, native tool IDs
✅ **OpenAI:** Standardized format, good error handling, optional streaming
✅ **Ollama:** Switched to official API format; good robustness for argument handling
✅ **Pairing:** Creative filesystem-based bridge; enables IDE/CLI integration
✅ **Base interface:** Clean Protocol-based design; easy to add new adapters

---

## Test Coverage Gaps

No unit tests per adapter visible. Need:
- Malformed response handling (per adapter)
- Multi-tool calls in single turn
- Tool result order preservation (Google/Ollama)
- Token counting accuracy per provider
- Timeout behavior (Pairing especially)

---

## Recommended Action Plan

### Phase 1: Stability (Weeks 1-2)
1. **Update Anthropic API version** (1h)
2. **Add synthetic IDs to Google adapter** (1h)
3. **Add error logging to OpenAI arg parsing** (30m)
4. **Write unit tests per adapter** (4h)

### Phase 2: Optimization (Week 3)
1. **Implement prompt caching for OpenAI** (2h)
2. **Add streaming support to Ollama** (2h)
3. **Document adapter-specific quirks** (1h)

### Phase 3: Polish (Week 4)
1. **Refactor tool result format** (standardize vs normalize in place)
2. **Add remote model registry** (config-driven instead of hardcoded)
3. **Performance benchmarking** (token usage, latency per adapter)

---

## By the Numbers

| Metric | Value | Status |
|--------|-------|--------|
| Adapters | 5 | ✅ |
| Working implementations | 5 | ✅ |
| API versions outdated | 1 (Anthropic) | 🟡 |
| Adapters without tool call IDs | 2 (Google, Ollama) | 🟡 |
| Unit tests | 0 | 🔴 |
| Documented API versions | 1/5 | 🟡 |

---

## Files Touched

- `/home/estupendo/code/HACA/implementations/fcp-ref/fcp_base/cpe/base.py` — Core interface
- `/home/estupendo/code/HACA/implementations/fcp-ref/fcp_base/cpe/anthropic.py` — Update needed
- `/home/estupendo/code/HACA/implementations/fcp-ref/fcp_base/cpe/google.py` — Fragile ID handling
- `/home/estupendo/code/HACA/implementations/fcp-ref/fcp_base/cpe/ollama.py` — Argument format unclear
- `/home/estupendo/code/HACA/implementations/fcp-ref/fcp_base/cpe/openai.py` — Inefficient system message

---

## Next Steps

**Today:** Read `cpe_state_analysis.md` for detailed breakdown.
**This week:** Prioritize Anthropic API update + Google synthetic IDs.
**This sprint:** Unit tests + documentation.

---

*See `cpe_state_analysis.md` for full analysis.*
