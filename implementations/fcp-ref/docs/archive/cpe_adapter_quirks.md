# CPE Adapter Quirks & Implementation Details

**Last Updated:** 2026-03-21
**Audience:** Developers extending or debugging CPE adapters

---

## Overview

This document captures adapter-specific implementation details, workarounds, and edge cases that aren't obvious from the code.

---

## Anthropic

### API Version
- **Current:** 2024-06-15 (Updated from 2023-06-01)
- **Supports:** Extended thinking, improved tool use, latest Claude models
- **Baseline:** claude-opus-4-6 (enterprise-grade reasoning)

### Message Format
- System message: Direct field in request body (not in messages array)
- Tool calls: Embedded in `content[]` array with type="tool_use"
- Each tool call has native `id` field provided by API

### Notable Behavior
- No prompt caching support (Anthropic handles optimization server-side)
- Tool results: FCP sends `[tool_name] {json}\n[tool_name] {json}` format; not native to API
- Idempotency: API supports idempotency keys (not used by FCP)

### Gotchas
- **Extended thinking:** Requires specific system prompt instruction; not automatic
- **Token counting:** Accurate; includes thinking tokens in output_tokens
- **Rate limiting:** Uses x-ratelimit-* headers (not parsed by current adapter)

---

## OpenAI

### API Version
- **Baseline:** gpt-4o (current best-in-class for reasoning)
- **Compatible endpoints:** Any OpenAI-compatible API (Azure, self-hosted)

### Message Format
- System message: Included in messages array with role="system"
- Tool calls: In message.tool_calls[] with function.arguments as JSON string
- Tool call IDs: Native `id` field (format: "call_*")

### Prompt Caching (2026-03-21)
- **Enabled for official OpenAI API only** (auto-detected: api.openai.com)
- **First invoke:** System message sent with cache_control={"type": "ephemeral"}
- **Subsequent invokes:** System message omitted (cached); saves ~100 tokens per call (~20% overhead reduction)
- **System change:** If system message differs, resend with cache_control (refreshes cache)
- **Compatibility:** Compatible endpoints don't support caching; system always included

### Tool Arguments Handling
- **Format:** JSON string, not dict
- **Edge case:** If JSON parse fails, logs warning to stderr and falls back to `{}`
- **Tool receives:** Empty dict on parse failure (silent fallback with visibility)

### Notable Behavior
- Token counting: Accurate; includes cache hit savings in usage.prompt_tokens
- Streaming: Not implemented (but interface supports it)
- Parallel tool calls: Full support via message.tool_calls[]

### Gotchas
- **None tool_calls:** If API returns tool_calls=null (explicit), must handle gracefully
- **No tool IDs in compatible endpoints:** Only official OpenAI provides IDs
- **Cache size limits:** Ephemeral cache ~2M tokens; not a concern for typical sessions

---

## Google Gemini

### API Version
- **Current:** gemini-2.0-flash (latest, supports thinking)
- **Base URL:** generativelanguage.googleapis.com/v1beta/models

### Message Format
- System instruction: Separate field (not in messages array)
- Tool calls: In message.parts[] with functionCall sub-object
- No native tool call IDs: FCP generates synthetic IDs ("call_0", "call_1", ...)

### Synthetic IDs (2026-03-21)
- **Why:** Google doesn't provide tool call IDs; order-based mapping is fragile
- **Implementation:** Index-based counter; ID = f"call_{index}"
- **Requirement:** Tool results MUST be returned in same order as calls
- **Risk:** If order violated, wrong tool receives wrong args

### Thinking Support
- **Format:** Separate parts[] entry with "thought" field
- **Parsing:** Filtered out by adapter (not exposed in CPEResponse.text)
- **Usage:** Useful for reasoning but not captured in current interface

### Tool Result Format
- **FCP sends:** `[tool_name] {json}\n[tool_name] {json}` text
- **Adapter converts:** To functionResponse parts with name + response.output
- **Edge case:** If tool result format unrecognized, treated as user message

### Notable Behavior
- Token counting: Includes thinking tokens
- Streaming: Not implemented (API supports it)
- Multi-turn conversations: Requires verbatim part preservation for thought_signature

### Gotchas
- **Order sensitivity:** If tool results come out of order, synthetic IDs don't help
- **Thought tokens:** High overhead for reasoning; not always needed
- **Function declaration format:** FCP uses OpenAI format; adapter converts to Gemini

---

## Ollama

### API Version
- **Baseline:** llama3.2 (default; configurable)
- **Base URL:** localhost:11434 (OLLAMA_BASE_URL to override)
- **Topology:** TRANSPARENT (local-only, no auth)

### Message Format
- System message: Included in messages array with role="system"
- Tool calls: In message.tool_calls[] (format synchronized with official API)
- Arguments: Can be dict OR JSON string (adapter normalizes both)
- No native IDs: FCP generates synthetic IDs

### Streaming Support (2026-03-21)
- **Status:** Optional; default disabled for backward compatibility
- **Enable:** Pass `enable_streaming=True` to OllamaAdapter
- **Format:** Each chunk is JSON object on separate line (newline-delimited JSON)
- **Accumulation:** Adapter merges chunks, extracts usage from final chunk
- **Tool calls:** Can appear in multiple chunks; accumulated across all

### Synthetic IDs (Same as Google)
- **Format:** "call_{index}"
- **Requirement:** Tool results must match call order
- **Risk:** Order violations cause argument misrouting

### Tool Result Format
- **FCP sends:** `[tool_name] {json}\n[tool_name] {json}` text
- **Adapter converts:** To role="tool" messages with tool_name + content
- **Edge case:** If unrecognized format, stays as user message

### Local Availability Check
- **Method:** `is_available()` pings `/api/tags` endpoint
- **Timeout:** 2 seconds
- **Use case:** Graceful fallback to other adapters if Ollama unavailable

### Notable Behavior
- Token counting: Accurate for local models
- No rate limiting: Local execution means unlimited capacity
- Model variety: Can use any Ollama-compatible model

### Gotchas
- **Streaming overhead:** Accumulating chunks in memory; not ideal for very long responses
- **JSON string args:** Some models return arguments as string, others as dict; both handled
- **No auth:** Design assumes Ollama runs locally; network exposure is a security risk
- **Tool support:** Not all Ollama models support function calling; verify model capabilities

---

## Pairing Adapter (Not in Phase 1-2)

### Topology
- **Type:** OPAQUE (filesystem-based MCP bridge)
- **Communication:** Marker files + stdin/stdout
- **Use case:** IDE/CLI integration; enables pair mode

### Notable Behavior
- No API calls; uses local process
- Sandbox: Full shell access within session scope
- Timeout: Configurable per call

---

## Cross-Adapter Considerations

### Synthetic IDs vs Native IDs
| Adapter | Native IDs | Synthetic | Pattern |
|---------|-----------|-----------|---------|
| Anthropic | ✅ Yes | N/A | Native |
| OpenAI | ✅ Yes | N/A | Native (call_*) |
| Google | ❌ No | ✅ Yes (2026) | call_0, call_1, ... |
| Ollama | ❌ No | ✅ Yes (2026) | call_0, call_1, ... |

### Tool Result Order Dependency
- **Adapters requiring order preservation:** Google, Ollama
- **Why:** No native IDs means order is the only mapping mechanism
- **Risk:** Out-of-order results cause arguments to mismatch tools
- **Mitigation:** FCP session loop maintains order; adapter assumes order preserved

### Error Handling
- **OpenAI JSON parse failures:** Log to stderr, fall back to {}
- **All adapters:** Missing fields default gracefully (not exceptions)
- **Network errors:** Raised as CPEError for session loop retry logic

### Token Counting Accuracy
| Adapter | Input | Output | Notes |
|---------|-------|--------|-------|
| Anthropic | ✅ Accurate | ✅ Accurate | Includes thinking tokens |
| OpenAI | ✅ Accurate | ✅ Accurate | Reflects cache hits |
| Google | ✅ Accurate | ✅ Accurate | Includes thinking tokens |
| Ollama | ✅ Accurate | ✅ Accurate | Local model dependent |

---

## Performance Tuning

### Token Overhead Reduction
1. **OpenAI:** Enable prompt caching (20% reduction for typical sessions)
2. **Ollama:** Enable streaming for long responses (reduces wait time)
3. **Anthropic:** No optimization available (server-side handled)

### Latency Considerations
- **Anthropic:** ~1-2s (API call + reasoning)
- **OpenAI:** ~1-3s (depends on model, cache state)
- **Google:** ~2-4s (reasoning overhead)
- **Ollama:** ~0.5-10s (depends on model, hardware)

### Memory Footprint
- **Streaming adapters (Ollama):** O(response_size) for chunk accumulation
- **Non-streaming:** Minimal (single response object)

---

## Testing Strategy

Each adapter is covered by:
1. **Parsing tests:** Validate response format → CPEResponse conversion
2. **Edge case tests:** Missing fields, null values, malformed data
3. **Tool call tests:** Single, multiple, with/without text
4. **Error handling tests:** JSON parse failures, network errors

See `tests/test_cpe_adapters.py` for full coverage.

---

## Future Work

### Phase 3 (Planned)
1. **Refactor tool result format:** Standardize vs normalize in place
2. **Remote model registry:** Config-driven instead of hardcoded defaults
3. **Performance benchmarking:** Token usage, latency per adapter
4. **Streaming for all adapters:** Not just Ollama
5. **Prompt caching for other adapters:** Anthropic uses server-side, Google has no mechanism

### Potential Improvements
- **Adaptive model selection:** Auto-choose best adapter based on task
- **Fallback chains:** If primary adapter unavailable, try secondary
- **Usage analytics:** Track token usage across sessions
- **Cost tracking:** Integrate pricing data (OpenAI especially)
