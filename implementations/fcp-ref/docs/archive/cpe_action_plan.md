# CPE Adapters — Detailed Action Plan

**Date:** 2026-03-21
**Scope:** Stabilize, test, optimize CPE layer
**Timeframe:** 4 weeks (P0, P1, P2 priority tiers)

---

## Week 1: Stability & Correctness

### P0-1: Update Anthropic API Version

**File:** `/home/estupendo/code/HACA/implementations/fcp-ref/fcp_base/cpe/anthropic.py`

**Current:**
```python
_API_VERSION = "2023-06-01"
```

**Action:**
1. Change to `_API_VERSION = "2024-06-15"`
2. Review Anthropic changelog for breaking changes
3. Test with Claude models:
   - claude-opus-4-6 (main)
   - claude-sonnet-4-6 (secondary)
   - claude-haiku-4-5-20251001 (lightweight)
4. Verify response format unchanged
5. Test extended thinking (if available in 2024-06-15)

**Checklist:**
- [ ] API version updated
- [ ] Anthropic changelog reviewed
- [ ] Unit tests pass
- [ ] Integration tests pass
- [ ] Extended thinking investigation documented

**Effort:** 1-2 hours
**Owner:** @dev
**Done when:** All tests pass, changelog reviewed

---

### P0-2: Add Error Logging to JSON Parse Failures

**Files:**
- `openai.py` (line 78-80)
- `ollama.py` (line 200-202)

**Current (OpenAI):**
```python
try:
    parsed_input = json.loads(raw_args)
except (json.JSONDecodeError, TypeError):
    parsed_input = {}  # Silent
```

**Action:**
1. Add logging import to both files:
   ```python
   import logging
   logger = logging.getLogger(__name__)
   ```

2. Replace silent fallback with:
   ```python
   try:
       parsed_input = json.loads(raw_args)
   except (json.JSONDecodeError, TypeError) as e:
       logger.warning(
           f"Tool argument parse failed for '{tool}'. "
           f"Raw: {raw_args[:100]!r}. Using empty dict. Error: {e}"
       )
       parsed_input = {}
   ```

3. Test with malformed JSON:
   ```python
   raw_args = '{"bad json'
   # Should log warning, not crash
   ```

**Checklist:**
- [ ] Logging added to openai.py
- [ ] Logging added to ollama.py
- [ ] Test with malformed JSON
- [ ] Verify log messages appear

**Effort:** 30 minutes
**Owner:** @dev
**Done when:** Warnings logged on parse failure; no silent failures

---

### P0-3: Add Synthetic IDs to Google Adapter

**File:** `/home/estupendo/code/HACA/implementations/fcp-ref/fcp_base/cpe/google.py`

**Current (line 193-196):**
```python
tool_calls.append(ToolUseCall(
    id="",  # Google doesn't provide IDs
    tool=fc.get("name", ""),
    input=fc.get("args", {}),
))
```

**Action:**
1. Change to:
   ```python
   for i, fc in enumerate(last_function_calls):
       tool_calls.append(ToolUseCall(
           id=f"google-{i:03d}",  # Synthetic: "google-000", "google-001", etc.
           tool=fc.get("name", ""),
           input=fc.get("args", {}),
       ))
   ```

2. Document in comments:
   ```python
   # Google API doesn't provide tool call IDs.
   # Generate synthetic IDs for tracking purposes.
   # Order MUST match order of function_calls in response.
   ```

3. Add test to verify IDs are sequential:
   ```python
   def test_google_synthetic_ids():
       # Multiple tool calls should get sequential IDs
       tool_calls = [...]
       assert tool_calls[0].id == "google-000"
       assert tool_calls[1].id == "google-001"
   ```

**Checklist:**
- [ ] Synthetic IDs added
- [ ] Comment explains why
- [ ] Unit test for ID generation
- [ ] Integration test with multi-tool call

**Effort:** 1 hour
**Owner:** @dev
**Done when:** IDs are generated; tests pass

---

### P0-4: Write Unit Tests Per Adapter

**Location:** `tests/cpe/` (create if not exists)

**Files to create:**
- `test_anthropic_adapter.py`
- `test_openai_adapter.py`
- `test_google_adapter.py`
- `test_ollama_adapter.py`
- `test_pairing_adapter.py`

**Per-adapter test template:**
```python
import unittest
from fcp_base.cpe import (CPEResponse, ToolUseCall)
from fcp_base.cpe.anthropic import _parse_response

class TestAnthropicAdapter(unittest.TestCase):

    def test_parse_response_with_tool_use(self):
        """Parse response with tool_use block."""
        data = {
            "content": [
                {"type": "text", "text": "Let me execute that."},
                {"type": "tool_use", "id": "123", "name": "fcp_exec",
                 "input": {"cmd": "ls"}}
            ],
            "usage": {"input_tokens": 100, "output_tokens": 50},
            "stop_reason": "tool_use"
        }
        resp = _parse_response(data)

        assert resp.text == "Let me execute that."
        assert len(resp.tool_use_calls) == 1
        assert resp.tool_use_calls[0].id == "123"
        assert resp.tool_use_calls[0].tool == "fcp_exec"
        assert resp.tool_use_calls[0].input == {"cmd": "ls"}
        assert resp.input_tokens == 100
        assert resp.stop_reason == "tool_use"

    def test_parse_empty_content(self):
        """Handle empty content array."""
        data = {
            "content": [],
            "usage": {"input_tokens": 0, "output_tokens": 0},
            "stop_reason": "end_turn"
        }
        resp = _parse_response(data)
        assert resp.text == ""
        assert len(resp.tool_use_calls) == 0

    def test_malformed_tool_input(self):
        """Handle malformed tool input gracefully."""
        data = {
            "content": [
                {"type": "tool_use", "id": "456", "name": "fcp_exec"}
                # Missing "input" field
            ],
            "usage": {"input_tokens": 10, "output_tokens": 5},
            "stop_reason": "tool_use"
        }
        resp = _parse_response(data)
        assert resp.tool_use_calls[0].input == {}  # Default
```

**Test categories per adapter:**
1. **Happy path:** Correct response format
2. **Edge cases:** Empty arrays, missing fields
3. **Parse failures:** Malformed JSON (OpenAI/Ollama)
4. **Multi-tool:** Multiple tool calls in single turn
5. **Token counting:** Correct token field mapping
6. **Error handling:** Network errors, auth errors, rate limits

**Coverage target:** ≥80% per adapter

**Checklist:**
- [ ] test_anthropic_adapter.py created (8 tests)
- [ ] test_openai_adapter.py created (10 tests)
- [ ] test_google_adapter.py created (9 tests)
- [ ] test_ollama_adapter.py created (10 tests)
- [ ] test_pairing_adapter.py created (6 tests)
- [ ] All tests pass
- [ ] Coverage ≥80%

**Effort:** 4-5 hours
**Owner:** @dev
**Done when:** Tests pass; coverage ≥80%

---

## Week 2: Documentation & Investigation

### P1-1: Document Anthropic Extended Thinking

**File:** Create `docs/anthropic_extended_thinking.md`

**Contents:**
1. Check if 2024-06-15 API supports extended thinking
2. If yes:
   - Document thinking token counting
   - Provide example prompts
   - Note any limitations
3. If no:
   - Document why it's not supported
   - Suggest upgrade path

**Checklist:**
- [ ] Anthropic API docs reviewed
- [ ] Investigation documented
- [ ] Example added (if supported)

**Effort:** 1 hour
**Owner:** @research
**Done when:** Documentation complete

---

### P1-2: Investigate Ollama Argument Format Inconsistency

**File:** Create `docs/ollama_investigation_report.md`

**Actions:**
1. Test multiple Ollama versions (if available)
2. Check Ollama GitHub issues
3. Determine:
   - Is arguments being dict vs JSON string a bug or feature?
   - Which Ollama versions have this behavior?
   - Should we normalize aggressively or log warning?
4. Document finding

**Example test:**
```bash
# Call Ollama chat endpoint with tool_declaration
# Observe arguments format in response
# Document which version, model, etc.
```

**Checklist:**
- [ ] Multiple Ollama versions tested
- [ ] GitHub issues checked
- [ ] Root cause identified
- [ ] Recommendation documented (log vs normalize)

**Effort:** 2-3 hours
**Owner:** @research
**Done when:** Root cause identified; recommendation clear

---

### P1-3: Create CPE Adapter Integration Guide

**File:** Create `docs/cpe_adapter_integration_guide.md`

**Sections:**
1. **Adding a new adapter:**
   - Protocol requirements
   - Response format expectations
   - Example (simple adapter)
2. **Testing a new adapter:**
   - Unit test template
   - Integration test flow
   - Deployment checklist
3. **Common pitfalls:**
   - Silent parse failures
   - Tool call ID handling
   - Token counting mapping
4. **Adapter-specific docs:**
   - API version tracking
   - Known issues
   - Optimization opportunities

**Checklist:**
- [ ] Template + example created
- [ ] Common pitfalls documented
- [ ] Linked from main docs

**Effort:** 2 hours
**Owner:** @docs
**Done when:** Guide complete; template tested

---

## Week 3: Optimization

### P2-1: Implement Prompt Caching for OpenAI

**File:** `/home/estupendo/code/HACA/implementations/fcp-ref/fcp_base/cpe/openai.py`

**Overview:**
OpenAI supports prompt caching to reduce token usage when system prompt and early messages are repeated.

**Implementation:**
```python
# Mark system message and tool definitions for caching
def invoke(self, system, messages, tools):
    full_messages = [{"role": "system", "content": system}] + messages

    # Mark first N messages as ephemeral for caching
    for msg in full_messages[:2]:  # System + first user message
        msg["cache_control"] = {"type": "ephemeral"}

    payload = {
        "model": self._model,
        "max_tokens": _MAX_TOKENS,
        "messages": full_messages,
    }
    if tools:
        payload["tools"] = tools
    return _parse_response(_post(...))
```

**Benefits:**
- ~50% reduction in system message tokens (estimated)
- ~10% overall token savings
- Faster response times (OpenAI caches processed context)

**Testing:**
1. Compare token usage before/after
2. Verify correctness with multiple turns
3. Measure latency improvement

**Checklist:**
- [ ] Cache control headers added
- [ ] Token usage compared
- [ ] Latency tested
- [ ] Documented in comments

**Effort:** 2-3 hours
**Owner:** @optimization
**Done when:** Caching active; token savings verified

---

### P2-2: Add Streaming Support to Ollama

**File:** `/home/estupendo/code/HACA/implementations/fcp-ref/fcp_base/cpe/ollama.py`

**Current:**
```python
"stream": False,  # Comment: "can enable streaming in future"
```

**Action:**
1. Add optional `stream` parameter:
   ```python
   def __init__(self, api_key: str = "", model: str = _DEFAULT_MODEL,
                base_url: str = "", stream: bool = False) -> None:
       self._stream = stream
   ```

2. Update invoke() to handle streaming:
   ```python
   payload["stream"] = self._stream

   if self._stream:
       return _parse_streaming_response(_post_stream(...))
   else:
       return _parse_response(_post(...))
   ```

3. Implement `_parse_streaming_response()`:
   - Read streaming chunks
   - Accumulate text and tool_calls
   - Return final CPEResponse

4. Test:
   - Compare output (streaming vs non-streaming)
   - Verify tool calls parsed correctly

**Benefit:**
- Streaming responses for longer outputs
- Lower perceived latency
- Potential for UI progress updates

**Checklist:**
- [ ] Streaming parameter added
- [ ] Streaming logic implemented
- [ ] Tests pass (streaming vs non-streaming)
- [ ] Documented in comments

**Effort:** 3 hours
**Owner:** @optimization
**Done when:** Streaming working; tests pass

---

### P2-3: Remote Model Registry

**File:** Create `fcp_base/cpe/model_registry.py`

**Purpose:**
Instead of hardcoded `KNOWN_MODELS`, fetch from remote registry.

**Implementation:**
```python
# model_registry.py
import json
import urllib.request

REGISTRY_URL = "https://raw.githubusercontent.com/anthropics/haca/main/model-registry.json"

def fetch_models(provider: str) -> list[str]:
    """Fetch model list from remote registry."""
    try:
        with urllib.request.urlopen(REGISTRY_URL, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            return data.get(provider, [])
    except Exception:
        # Fallback to local hardcoded list
        return _LOCAL_MODELS.get(provider, [])
```

**Benefits:**
- Models stay up-to-date without code changes
- New models can be added to registry without deploy
- Community can maintain model list

**Checklist:**
- [ ] Registry URL setup (GitHub or other)
- [ ] Fallback logic implemented
- [ ] Tested with network down
- [ ] Documentation updated

**Effort:** 2 hours
**Owner:** @infra
**Done when:** Fetching models remotely; fallback working

---

## Week 4: Polish & Docs

### P3-1: Refactor Tool Result Format

**Goal:** Normalize tool result handling across adapters.

**Current problem:**
- Anthropic/OpenAI: '[tool] {json}' in user message
- Google: functionResponse parts
- Ollama: role: tool messages
- Pairing: depends on external agent

**Solution:** Normalize in adapter before sending to CPE:
1. FCP sends '[tool] {json}' format (current)
2. Each adapter converts to its native format (already done)
3. Document this contract

**No code change needed,** just document.

**Checklist:**
- [ ] Document in `cpe_adapter_integration_guide.md`
- [ ] Example per adapter included
- [ ] Linked from main docs

**Effort:** 1 hour
**Owner:** @docs
**Done when:** Documented clearly

---

### P3-2: Performance Benchmarking

**File:** Create `tests/benchmarks/cpe_benchmarks.py`

**Metrics:**
1. Token usage per adapter
2. Latency per adapter
3. Error rate
4. Cache hit rate (OpenAI)

**Script:**
```python
import time
from fcp_base.cpe import make_adapter

adapters = [
    ("anthropic", AnthropicAdapter(...)),
    ("openai", OpenAIAdapter(...)),
    ("ollama", OllamaAdapter(...)),
]

for name, adapter in adapters:
    start = time.time()
    resp = adapter.invoke(SYSTEM, MESSAGES, TOOLS)
    elapsed = time.time() - start

    print(f"{name}:")
    print(f"  Latency: {elapsed:.2f}s")
    print(f"  In tokens: {resp.input_tokens}")
    print(f"  Out tokens: {resp.output_tokens}")
```

**Checklist:**
- [ ] Benchmark script created
- [ ] All adapters benchmarked
- [ ] Results documented
- [ ] Baseline established (for future regressions)

**Effort:** 2 hours
**Owner:** @perf
**Done when:** Benchmarks documented

---

### P3-3: Final Documentation Pass

**Files to review/update:**
1. `docs/cpe_state_analysis.md` — Update with changes
2. `docs/cpe_comparison_matrix.md` — Update scores
3. `docs/cpe_adapter_integration_guide.md` — Link from main docs
4. `README.md` — Add CPE section

**Checklist:**
- [ ] State analysis updated
- [ ] Comparison matrix scores revised
- [ ] Integration guide added
- [ ] README links to docs

**Effort:** 1-2 hours
**Owner:** @docs
**Done when:** All docs reviewed; no broken links

---

## Success Criteria

By end of week 4:

✅ **Stability:**
- Anthropic API updated to 2024-06-15
- All 5 adapters have synthetic or real IDs
- No silent failures (logging added)

✅ **Testing:**
- Unit tests for all adapters (≥80% coverage)
- Integration tests for multi-tool scenarios
- All tests passing

✅ **Documentation:**
- Adapter comparison matrix complete
- Integration guide for new adapters
- Performance benchmark baseline
- No broken links

✅ **Optimization:**
- OpenAI prompt caching (if implemented)
- Ollama streaming (if implemented)
- Remote model registry (if implemented)

---

## Risks & Mitigation

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|-----------|
| Anthropic API version update breaks | Low | High | Thorough testing before release |
| Google synthetic ID ordering fails | Medium | High | Add assertion in tests |
| Ollama investigation inconclusive | Medium | Low | Document as "TBD" |
| Tests are hard to write | Medium | Medium | Use provided templates |

---

## Resource Allocation

**Dev capacity needed:** ~40 hours over 4 weeks
- Week 1: 8h (P0 items)
- Week 2: 6h (P1 docs/investigation)
- Week 3: 6h (P2 optimization)
- Week 4: 4h (P3 polish)

**Roles:**
- @dev: Weeks 1-2 (code changes)
- @research: Weeks 1-2 (investigation)
- @optimization: Week 3 (Ollama streaming, OpenAI caching)
- @docs: Weeks 2, 4 (documentation)
- @perf: Week 4 (benchmarking)

---

## Done Definition

Each task is "done" when:
1. **Code:** Changes committed + tests passing
2. **Documentation:** Added + reviewed + links correct
3. **Testing:** Unit tests ≥80%; integration tests pass
4. **Review:** At least one review + addressed feedback

---

## Escalation

If stuck on:
- **Anthropic API:** Check changelog directly; contact Anthropic support if needed
- **Google IDs:** Ask if Google plans to add ID support in future API version
- **Ollama format:** Check latest Ollama GitHub for known issues
- **Performance:** Profile with cProfile; identify bottlenecks

---

**Next step:** Schedule week 1 work; assign @dev to Anthropic API update.
