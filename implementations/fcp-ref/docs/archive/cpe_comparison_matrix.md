# CPE Adapters — Comparison Matrix & Visual Guide

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         FCP Session Loop                         │
│  (Manages system, messages, tools, retry logic)                  │
└───────────────────────────┬─────────────────────────────────────┘
                            │ invoke(system, messages, tools)
                            ▼
            ┌───────────────────────────────────┐
            │   CPEAdapter (Protocol)            │
            │  - invoke()                        │
            │  - returns: CPEResponse            │
            └────────┬────────────────────────────┘
                     │
        ┌────────────┼────────────┬────────────┬────────────┐
        ▼            ▼            ▼            ▼            ▼
   ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐
   │Anthropic│ │ OpenAI  │ │ Google  │ │ Ollama  │ │Pairing  │
   │Adapter  │ │Adapter  │ │Adapter  │ │Adapter  │ │Adapter  │
   └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘
        │            │           │           │           │
        ▼            ▼           ▼           ▼           ▼
   ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐
   │Anthropic│ │ OpenAI  │ │ Google  │ │ Ollama  │ │MCP Server│
   │API      │ │API      │ │Gemini   │ │local    │ │(external)│
   │v2023-06 │ │v2024    │ │v1beta   │ │/api/chat│ │/api      │
   └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘
```

---

## Tool Calling — Flow Diagram

### Anthropic
```
Model response:
  ├─ content[0]: {type: "text", text: "..."}
  └─ content[1]: {type: "tool_use", id: "X", name: "fcp_exec", input: {...}}

Adapter parsing:
  └─ ToolUseCall(id="X", tool="fcp_exec", input={...})  ✅ Direct dict
```

### OpenAI
```
Model response:
  └─ choices[0].message: {
       content: "...",
       tool_calls: [{
         id: "call_123",
         function: {name: "fcp_exec", arguments: '{"cmd":"ls"}'}  ← JSON string
       }]
     }

Adapter parsing:
  └─ json.loads(arguments) → ToolUseCall(id="call_123", tool="fcp_exec", input={...})
     ⚠️  Can fail silently → empty dict
```

### Google
```
Model response:
  └─ candidates[0].content.parts: [
       {text: "..."},
       {functionCall: {name: "fcp_exec", args: {...}}}  ← Direct dict
     ]

Adapter parsing:
  ├─ Stores last_function_calls for next turn
  └─ ToolUseCall(id="", tool="fcp_exec", input={...})
     ⚠️  No ID — order-dependent mapping
```

### Ollama
```
Model response:
  └─ message: {
       content: "...",
       tool_calls: [{
         function: {
           name: "fcp_exec",
           arguments: {...} or '...'  ← Can be either!
         }
       }]
     }

Adapter parsing:
  └─ if isinstance(arguments, str): json.loads(arguments)
  └─ ToolUseCall(id="", tool="fcp_exec", input={...})
     ⚠️  No ID — order-dependent; Argument format inconsistent
```

### Pairing
```
Request file (~/.fcp/pairing/session.request.json):
  ├─ system: "..."
  ├─ messages: [...]
  └─ tools: [...]

External agent processes and writes response file:
  └─ response: {
       text: "...",
       tool_use_calls: [{id: "...", tool: "...", input: {...}}],
       stop_reason: "..."
     }

Adapter parsing:
  └─ Direct ToolUseCall reconstruction
     ✅ Depends on external agent
```

---

## Tool Result Format — How Each Adapter Handles Them

### Anthropic
```
FCP sends (user message):
  "content": "[fcp_exec] {\"stdout\": \"bin...\"}\n[fcp_mil] {\"code\": \"...\"}"

Anthropic receives:
  └─ Interprets as user text (no special handling needed)
```

### OpenAI
```
FCP sends (user message):
  "content": "[fcp_exec] {...}\n[fcp_mil] {...}"

OpenAI receives:
  └─ Interprets as user text
  └─ No tool_calls in response (tool results are treated as text)
```

### Google
```
FCP sends (user message):
  "content": "[fcp_exec] {...}\n[fcp_mil] {...}"

Adapter intercepts and converts to:
  └─ {
       role: "user",
       parts: [
         {functionResponse: {name: "fcp_exec", response: {...}}},
         {functionResponse: {name: "fcp_mil", response: {...}}}
       ]
     }

Google receives:
  └─ Proper functionResponse format (custom per Google)
```

### Ollama
```
FCP sends (user message):
  "content": "[fcp_exec] {...}\n[fcp_mil] {...}"

Adapter converts to:
  └─ [
       {role: "tool", tool_name: "fcp_exec", content: "{...}"},
       {role: "tool", tool_name: "fcp_mil", content: "{...}"}
     ]

Ollama receives:
  └─ Proper role: tool messages (standard for local models)
```

### Pairing
```
FCP sends (user message):
  "content": "[fcp_exec] {...}"

External agent receives:
  └─ Full context (system, messages, tools)
  └─ Agent parses tool results as needed (their responsibility)
```

---

## Response Format Comparison

### By API Structure

| Provider | Top Level | Main Content | Tool Call Location |
|----------|-----------|--------------|-------------------|
| **Anthropic** | `content[]` | Array | `content[].type="tool_use"` |
| **OpenAI** | `choices[]` | `message` object | `message.tool_calls[]` |
| **Google** | `candidates[]` | `content.parts[]` | `parts[].functionCall` |
| **Ollama** | `message` | Flat object | `message.tool_calls[]` |
| **Pairing** | Custom JSON | Flat object | `tool_use_calls[]` |

### By Token Counting

| Provider | Input Token Field | Output Token Field |
|----------|-------------------|--------------------|
| **Anthropic** | `usage.input_tokens` | `usage.output_tokens` |
| **OpenAI** | `usage.prompt_tokens` | `usage.completion_tokens` |
| **Google** | `usageMetadata.promptTokenCount` | `usageMetadata.candidatesTokenCount` |
| **Ollama** | `prompt_eval_count` | `eval_count` |
| **Pairing** | `input_tokens` (optional) | `output_tokens` (optional) |

---

## Detailed Comparison Matrix

### API Compliance & Stability

```
┌──────────────┬──────────────┬─────────────┬──────────────┐
│ Provider     │ API Version  │ Status      │ Risks        │
├──────────────┼──────────────┼─────────────┼──────────────┤
│ Anthropic    │ 2023-06-01   │ 🟡 Outdated │ API changes  │
│              │ (2yr old)    │             │ not tracked  │
├──────────────┼──────────────┼─────────────┼──────────────┤
│ OpenAI       │ 2024         │ ✅ Current  │ None         │
├──────────────┼──────────────┼─────────────┼──────────────┤
│ Google       │ v1beta       │ 🟡 Exp.     │ Breaking     │
│              │ (Unstable)   │             │ changes      │
├──────────────┼──────────────┼─────────────┼──────────────┤
│ Ollama       │ Latest       │ ✅ Current  │ Local only   │
├──────────────┼──────────────┼─────────────┼──────────────┤
│ Pairing      │ N/A          │ ✅ Stable   │ FS race cond │
└──────────────┴──────────────┴─────────────┴──────────────┘
```

### Tool Calling Features

```
┌──────────────┬─────────┬──────────┬─────────────┬─────────────┐
│ Capability   │ Anthrop │ OpenAI   │ Google      │ Ollama      │
├──────────────┼─────────┼──────────┼─────────────┼─────────────┤
│ Tool IDs     │ ✅ Yes  │ ✅ Yes   │ ❌ No       │ ❌ No       │
│ Parallel     │ ✅ Yes  │ ✅ Yes   │ ⚠️ Order    │ ✅ Yes      │
│ Multiple     │ ✅ Multi│ ✅ Multi │ ⚠️ Fragile  │ ✅ Multi    │
│ Args as dict │ ✅ Yes  │ ❌ String│ ✅ Yes      │ ⚠️ Both     │
│ Parse robust │ ✅ Simple│❌ Fallback│ ✅ Direct │ ⚠️ Inconsist│
└──────────────┴─────────┴──────────┴─────────────┴─────────────┘
```

### Performance Characteristics

```
┌──────────────┬──────────────┬──────────────┬─────────────┐
│ Metric       │ Anthropic    │ OpenAI       │ Ollama      │
├──────────────┼──────────────┼──────────────┼─────────────┤
│ Latency      │ High (API)   │ High (API)   │ Low (local) │
│ System msg   │ Separate     │ Injected ⚠   │ Injected    │
│ Streaming    │ Not impl     │ Supported    │ Not impl    │
│ Token waste  │ None         │ ~100+ per    │ None        │
│              │              │ request      │             │
└──────────────┴──────────────┴──────────────┴─────────────┘
```

---

## Error Handling Comparison

### Auth Errors
```
All adapters:
  └─ Check API key in __init__
  └─ If missing: raise CPEAuthError
  └─ HTTP 401: caught by _http.py, re-raised as CPEAuthError
```

### Rate Limits
```
All adapters (via _http.py):
  └─ HTTP 429 → CPERateLimitError
  └─ Session loop handles retry with backoff
```

### Parse Errors

| Provider | Behavior | Risk |
|----------|----------|------|
| Anthropic | No JSON parsing needed | ✅ Safe |
| OpenAI | `json.loads()` with fallback to `{}` | ⚠️ Silent |
| Google | No JSON parsing needed | ✅ Safe |
| Ollama | `json.loads()` with fallback to `{}` | ⚠️ Silent |
| Pairing | No parsing (external agent) | Depends |

---

## State & Statefulness

```
┌──────────────┬─────────────┬──────────────────────────────┐
│ Provider     │ Stateful?   │ What's tracked               │
├──────────────┼─────────────┼──────────────────────────────┤
│ Anthropic    │ ❌ No       │ Nothing (stateless)          │
│ OpenAI       │ ❌ No       │ Nothing (stateless)          │
│ Google       │ ✅ YES      │ _last_model_parts            │
│              │             │ _last_function_calls        │
│              │             │ (for tool result mapping)    │
│ Ollama       │ ❌ No       │ Nothing (stateless)          │
│ Pairing      │ ✅ YES      │ session_id, meta file, key   │
│              │             │ request/response files       │
└──────────────┴─────────────┴──────────────────────────────┘
```

**Note:** Google's statefulness is a smell—better to use IDs.

---

## Configuration & Initialization

```python
# Anthropic
AnthropicAdapter(api_key="sk-...", model="claude-opus-4-6")
  ├─ Reads ANTHROPIC_API_KEY env if not provided
  └─ Model is required (no default in factory)

# OpenAI
OpenAIAdapter(api_key="sk-...", model="gpt-4o")
  ├─ Reads OPENAI_API_KEY env
  ├─ Reads OPENAI_BASE_URL env (default: https://api.openai.com/v1)
  └─ Supports custom base URLs (OpenAI-compatible endpoints)

# Google
GoogleAdapter(api_key="AIza...", model="gemini-2.0-flash")
  ├─ Reads GOOGLE_API_KEY env
  └─ API key passed via query param (not header)

# Ollama
OllamaAdapter(api_key="", model="llama3.2")
  ├─ No API key needed
  ├─ Reads OLLAMA_BASE_URL env (default: http://localhost:11434)
  ├─ Has .is_available() check
  └─ Dynamically populates KNOWN_MODELS

# Pairing
PairingAdapter(api_key="", model="external", layout=Layout)
  ├─ No API key needed
  ├─ Needs Layout for hook integration
  ├─ Generates session_id & key
  └─ Creates ~/.fcp/pairing files
```

---

## Decision Matrix: Which Adapter to Use?

```
┌─────────────────────────────────────────────────────────────┐
│ Choose ANTHROPIC if:                                        │
│  • Using Claude exclusively                                 │
│  • Want simplest tool calling API                           │
│  • Don't mind higher costs                                  │
│ ⚠️  Fix API version first (2023 → 2024)                    │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ Choose OPENAI if:                                           │
│  • Want flexibility (gpt-4o, 4-mini, o3)                    │
│  • Using OpenAI-compatible endpoints                        │
│  • Standardized API most important                          │
│ ⚠️  System message injection wastes tokens (fixable)       │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ Choose GOOGLE if:                                           │
│  • Testing with Gemini                                      │
│  • Willing to work around no-ID limitation                  │
│ ⚠️  API is v1beta (experimental)                           │
│ ⚠️  Add synthetic IDs before production                     │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ Choose OLLAMA if:                                           │
│  • Running locally (no API key needed)                      │
│  • Want low latency                                         │
│  • Testing offline                                          │
│ ⚠️  No streaming (waits for full response)                 │
│ ⚠️  Arguments format inconsistency (investigate)            │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ Choose PAIRING if:                                          │
│  • Integrating with IDE/CLI via MCP                         │
│  • Want human-in-loop capability                            │
│  • Delegating to external agent                             │
│ ✅ Well-designed; creative FS-based bridge                 │
└─────────────────────────────────────────────────────────────┘
```

---

## Summary Scorecard

```
            Quality  Stability  Maturity  Perf  Docs
────────────────────────────────────────────────────
Anthropic   ✅ A     🟡 B       ✅ A      ✅ A  🔴 F
OpenAI      ✅ A     ✅ A+      ✅ A      🟡 B  ✅ A
Google      ✅ A     🟡 B-      🟡 B      ✅ A  🔴 F
Ollama      🟡 B     ✅ A       🟡 B      ✅ A+ 🔴 F
Pairing     ✅ A     ✅ A       🟡 B      🟡 B  🟡 C
────────────────────────────────────────────────────
Overall     ✅ A-    🟡 B       🟡 B      ✅ A  🔴 F
```

---

*For detailed analysis, see `cpe_state_analysis.md`*
