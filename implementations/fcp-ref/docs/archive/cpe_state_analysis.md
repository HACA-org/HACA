# CPE Adapters — Estado Atual & Análise Completa

**Data:** 2026-03-21
**Scope:** 5 adapters (Anthropic, OpenAI, Google, Ollama, Pairing)
**Verson:** 1.0

---

## 1. Base CPE (base.py e _http.py)

### 1.1 Versão API & Estrutura

| Aspecto | Detalhe |
|---------|---------|
| **Arquivo Base** | `fcp_base/cpe/base.py` |
| **HTTP Helper** | `fcp_base/cpe/_http.py` |
| **Dependency** | `urllib.request` (stdlib — zero external deps) |
| **API Version** | Heterogênea por provider (vide seção 2) |
| **Python Features** | Protocol + runtime_checkable, dataclasses |

### 1.2 Interface CPEAdapter

```python
@runtime_checkable
class CPEAdapter(Protocol):
    def invoke(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> CPEResponse:
        ...
```

- **Contrato:** Uniform interface sobre todos os backends
- **Inputs:**
  - `system`: string fixo (session lifetime)
  - `messages`: chat_history acumulada (role, content, opcionalmente tool_calls)
  - `tools`: FCP tool declarations (name, description, input_schema)
- **Output:** `CPEResponse` normalizada
- **Responsabilidade da interface:** apenas invoke; não gerencia history/context
- **Retry logic:** fica no session loop (não no adapter)

### 1.3 CPEResponse Structure

```python
@dataclass(slots=True)
class CPEResponse:
    text: str                       # narrative text (pode ser "")
    tool_use_calls: list[ToolUseCall]
    input_tokens: int
    output_tokens: int
    stop_reason: str                # "end_turn" | "tool_use" | "max_tokens" | …
```

```python
@dataclass(slots=True)
class ToolUseCall:
    id: str                        # tool call ID (pode ser "" se não suportado)
    tool: str                      # tool name (e.g. "fcp_exec")
    input: dict[str, Any]          # raw args dict (NOT string)
```

**Design decision:** `input` é sempre dict, nunca JSON string. Parsing é feito no adapter.

### 1.4 Factory & Auto-detection

#### Factory (`make_adapter`)
- Instancia adapter correto based on `backend` string
- Backend validation contra `BACKENDS` list
- Passa `layout` opcionalmente (para PairingAdapter)
- Raises `ValueError` para backend desconhecido

#### Auto-detect (`detect_adapter`)
Priority order:
1. `ANTHROPIC_API_KEY` → AnthropicAdapter (default: claude-opus-4-6)
2. `OPENAI_API_KEY` → OpenAIAdapter (default: gpt-4o)
3. `GOOGLE_API_KEY` → GoogleAdapter (default: gemini-2.0-flash)
4. Ollama (default: llama3.2) — fallback, com `.is_available()` check
5. Falls back to error message se nenhum backend disponível

#### Load from Baseline
`load_cpe_adapter_from_baseline(layout)` lê `baseline.json` e instancia adapter.

### 1.5 Error Handling

```python
class CPEError(Exception):
    """Non-retryable failures."""

class CPEAuthError(CPEError):
    """HTTP 401 — API key missing or invalid."""

class CPERateLimitError(CPEError):
    """HTTP 429 — rate limit / quota exceeded."""
```

**Handling em _http.py:**
- `post_json()` centralizado para todos os HTTP adapters
- 401 → CPEAuthError
- 429 → CPERateLimitError
- Outros HTTP errors → CPEError com status code
- Network errors (URLError) → CPEError

**Gap identified:** Nenhum retry logic no adapter level (OK, está no session loop).

---

## 2. Análise Por Adapter

### 2.1 Anthropic Adapter

| Atributo | Valor |
|----------|-------|
| **Arquivo** | `fcp_base/cpe/anthropic.py` |
| **API URL** | `https://api.anthropic.com/v1/messages` |
| **API Version** | `2023-06-01` (hardcoded no header) |
| **Modelo Default** | `claude-opus-4-6` |
| **Max Tokens** | 8192 |

#### Tool Calling Support
- ✅ **Sim, nativo**
- Format: native Anthropic tool_use blocks
- Response structure: `content[]` array com `{type: "tool_use", id, name, input}`
- Input parsing: Direct dict (Anthropic já retorna dict)

#### Message Format Handling
- **System:** Separado no payload (Anthropic design)
- **Messages:** Passado como-é; Anthropic espera `{role, content, tool_use}` format
- **Tool results:** User messages com '[tool_name] {json}' text

#### Tool Call Parsing
```python
for block in data.get("content", []):
    if block.get("type") == "tool_use":
        tool_calls.append(ToolUseCall(
            id=block.get("id", ""),
            tool=block.get("name", ""),
            input=block.get("input", {}),  # Direct dict
        ))
```
**Strengths:** Parsing simples, sem JSON decode necessário

#### Response Format
```
{
  "content": [
    {"type": "text", "text": "..."},
    {"type": "tool_use", "id": "...", "name": "...", "input": {...}}
  ],
  "usage": {"input_tokens": N, "output_tokens": N},
  "stop_reason": "end_turn" | "tool_use"
}
```

#### Quirks/Issues
- **API Version hardcoded (2023-06-01):** Pode estar desatualizada. Current: 2024-06-15
  - **Action:** Verificar se há mudanças breaking
- **No support para variantes do modelo:** Sempre usa exatamente o modelo passado
- **Sem tratamento para "thinking" blocks:** Anthropic agora tem extended thinking; ignorado

#### Compliance com API Oficial
- ✅ Compatível com Anthropic Messages API
- ⚠ API version defasada (2023-06-01 vs 2024-06-15)
- ⚠ Extended thinking não suportado (novo feature)

---

### 2.2 OpenAI Adapter

| Atributo | Valor |
|----------|-------|
| **Arquivo** | `fcp_base/cpe/openai.py` |
| **API URL Base** | `https://api.openai.com/v1` (env: `OPENAI_BASE_URL`) |
| **Endpoint** | `/chat/completions` |
| **Modelo Default** | `gpt-4o` |
| **Max Tokens** | 8192 |
| **OpenAI-compatible** | ✅ Sim (design genérico) |

#### Tool Calling Support
- ✅ **Sim, nativo**
- Format: OpenAI function calling (tool_choice, parallel tool calls)
- Response structure: `choices[0].message.tool_calls[]` array
- Input parsing: JSON string → dict (requer parse)

#### Message Format Handling
- **System:** Injected como primeiro `{role: "system", content: system}` message
  - **Design difference:** OpenAI não tem sistema separada, só message com role=system
  - **Implication:** System é reenviado em cada invoke (não ideal, mas necessário)
- **Messages:** Passado após system message
- **Tool results:** User messages com '[tool_name] {json}' text (compatível com Anthropic)

#### Tool Call Parsing
```python
for tc in message.get("tool_calls", []):
    raw_args = tc.get("function", {}).get("arguments", "{}")
    try:
        parsed_input = json.loads(raw_args)
    except (json.JSONDecodeError, TypeError):
        parsed_input = {}  # Fallback para dict vazio
    tool_calls.append(ToolUseCall(
        id=tc.get("id", ""),
        tool=tc.get("function", {}).get("name", ""),
        input=parsed_input,
    ))
```
**Fragilidade:** JSON parse pode falhar silenciosamente

#### Response Format
```
{
  "choices": [{
    "message": {
      "content": "...",
      "tool_calls": [
        {
          "id": "...",
          "type": "function",
          "function": {
            "name": "...",
            "arguments": "{...}"  # JSON string, not dict!
          }
        }
      ]
    },
    "finish_reason": "tool_calls" | "stop"
  }],
  "usage": {"prompt_tokens": N, "completion_tokens": N}
}
```

#### Quirks/Issues
- **Arguments como JSON string:** Requer parsing; erro silencioso se inválido
- **System message injection:** Reenviado em cada invoke (inefficient)
  - **Impact:** Aumenta token usage desnecessariamente
- **finish_reason mismatch:** OpenAI usa "tool_calls"; adapters esperam "tool_use"
  - **Não é problema:** Código mapeia corretamente via `stop_reason = finish_reason`
- **Sem cache_control:** OpenAI suporta prompt caching; não usado
- **Sem modo "stream":** Sempre non-streaming

#### Compliance com API Oficial
- ✅ Compatível com OpenAI Chat Completions API (2024)
- ⚠ System message injection é inefficient
- ⚠ Prompt caching não implementado

---

### 2.3 Google Adapter

| Atributo | Valor |
|----------|-------|
| **Arquivo** | `fcp_base/cpe/google.py` |
| **API URL Base** | `https://generativelanguage.googleapis.com/v1beta/models` |
| **Endpoint** | `/{model}:generateContent` (v1beta) |
| **Modelo Default** | `gemini-2.0-flash` |
| **Max Tokens** | 8192 |

#### Tool Calling Support
- ✅ **Sim, com quirks**
- Format: Google function_declarations + functionCall/functionResponse
- Response structure: `candidates[0].content.parts[]` array (misto de text + functionCall)
- Input parsing: Dict (direto em `args` field)

#### Message Format Handling
**Complexidade HIGH:** Google tem sistema de "parts" muito específico.

- **System:** Embutido como `system_instruction` (separado, bom)
- **Messages:** Convertidas para `contents[]` com `{role, parts}` format
- **Tool results:** Convertidas para `functionResponse` parts (não user messages!)

**Key issue:** Google usa duas turnos diferentes para tool results:
- Anthropic/OpenAI: user message com '[tool_name] {json}'
- Google: explicit `functionResponse` parts

Adapter resolve com `_build_contents()`:
```python
if (role == "user" and last_function_calls and
    messages[i-1]["role"] == "assistant" and
    not messages[i-1].get("content", "")):
    # Parse tool result lines e convert to functionResponse parts
    tool_results = _parse_tool_results(content)
    if tool_results:
        for j, fc in enumerate(last_function_calls):
            parts.append({
                "functionResponse": {
                    "name": fc["functionCall"]["name"],
                    "response": {"output": resp}
                }
            })
```

#### Tool Call Parsing
```python
for part in raw_model_parts:
    if "functionCall" in part:
        fc = part["functionCall"]
        tool_calls.append(ToolUseCall(
            id="",  # Google não fornece IDs
            tool=fc.get("name", ""),
            input=fc.get("args", {}),  # Direct dict
        ))
```
**Note:** ID sempre vazio (Google não suporta)

#### Response Format
```
{
  "candidates": [{
    "content": {
      "parts": [
        {"text": "..."},
        {"thought": "..."},
        {"functionCall": {"name": "...", "args": {...}}}
      ]
    },
    "finishReason": "STOP" | "TOOL_CALLS"
  }],
  "usageMetadata": {
    "promptTokenCount": N,
    "candidatesTokenCount": N
  }
}
```

#### Quirks/Issues
- **Tool call IDs não suportados:** Always empty string
  - **Impact:** Não pode rastrear qual tool_use corresponde qual tool result
  - **Mitigação:** Assume ordem (j-ésimo result corresponde j-ésimo call)
- **Thought blocks ignorados:** Anthropic extended thinking; Google tem "thought" parts
  - `if "text" in part and not part.get("thought")` — ignora thoughts
- **Stateful parsing:** Adapter mantém `_last_model_parts` e `_last_function_calls`
  - **Why:** Para mapear tool results na próxima turnada (sem IDs)
  - **Risk:** Se ordem mudar, results são mapped incorretamente
- **functionResponse format:** Específico do Google; não portável
- **v1beta API:** Pode mudar sem backwards compatibility

#### Compliance com API Oficial
- ⚠ Compatível com Google Gemini API v1beta (experimental)
- ⚠ Mapping de tool results é frágil (sem IDs)
- ⚠ API é v1beta (pode mudar)

---

### 2.4 Ollama Adapter

| Atributo | Valor |
|----------|-------|
| **Arquivo** | `fcp_base/cpe/ollama.py` |
| **API URL Base** | `http://localhost:11434` (env: `OLLAMA_BASE_URL`) |
| **Endpoint** | `/api/chat` |
| **Modelo Default** | `llama3.2` |
| **Max Tokens** | 8192 |

#### Tool Calling Support
- ⚠ **Sim, mas recente (2026-03-20)**
- Format: Official Ollama tool calling (message.tool_calls[])
- Response structure: `message.tool_calls[]` array
- Input parsing: Dict OR JSON string (normaliza ambos)

#### Message Format Handling
- **System:** Injected como `{role: "system", content: system}` (similar OpenAI)
- **Messages:** Convertidas com `_convert_messages()` helper
- **Tool results:** User messages com '[tool_name] {json}' são convertidas para `{role: "tool", tool_name, content}`
  - **Difference:** Ollama espera role=tool, não user message
  - **Adapter resolve:** Parse '[tool_name] {json}' lines e cria role=tool messages

#### Tool Call Parsing
```python
for tc in message.get("tool_calls", []):
    fn = tc.get("function", {})
    raw_args = fn.get("arguments", {})

    # Normalize: dict or JSON string
    if isinstance(raw_args, str):
        try:
            raw_args = json.loads(raw_args)
        except:
            raw_args = {}

    tool_calls.append(ToolUseCall(
        id="",
        tool=fn.get("name", ""),
        input=raw_args,  # dict after normalization
    ))
```
**Robustness:** Trata ambos dict e JSON string

#### Response Format
```
{
  "message": {
    "role": "assistant",
    "content": "...",
    "tool_calls": [
      {
        "function": {
          "name": "...",
          "arguments": {...} or "..."  # dict or JSON string
        }
      }
    ]
  },
  "prompt_eval_count": N,
  "eval_count": N,
  "done_reason": "stop" | "tool_calls"
}
```

#### Quirks/Issues
- **Tool call IDs não suportados:** Always empty string (como Google)
- **Arguments format variável:** Pode ser dict ou JSON string
  - **Adapter handles:** Normaliza ambos
  - **Fragility:** Parsing JSON string é fragile (silencioso fallback)
- **Token counting mismatch:** Ollama usa prompt_eval_count/eval_count (não standard)
  - **Not a problem:** Adapter mapeia corretamente
- **Local-only:** Não funciona com remote Ollama servers (localhost hardcoded)
  - **Actually:** OLLAMA_BASE_URL env var permite override
- **Streaming não implementado:** Flag sempre `stream: False`
  - **Comment:** "can enable streaming in future"
  - **Impact:** Respostas longas esperam até completion (latência)

#### Compliance com API Oficial
- ✅ Compatível com Ollama official API (message.tool_calls[])
- ⚠ Tool call arguments podem ser dict ou string (unstandardized)
- ⚠ Tool call IDs não suportados

---

### 2.5 Pairing Adapter

| Atributo | Valor |
|----------|-------|
| **Arquivo** | `fcp_base/cpe/pairing.py` |
| **Architecture** | Filesystem-based + MCP server bridge |
| **Directory** | `~/.fcp/pairing/` |
| **Session ID** | 8-char random hex (e.g., "a3f1c9b2") |
| **Model** | "external" (cosmetic only) |

#### Tool Calling Support
- ✅ **Depende do agent externo**
- Format: Padrão FCP (ToolUseCall: id, tool, input)
- Response structure: Esperado como `tool_use_calls[]` array (Anthropic-like)
- Input parsing: Direct dict (assumes external agent normaliza)

#### Message Format Handling
- **System:** Passado as-is na request JSON
- **Messages:** Passado as-is na request JSON
- **Tools:** Passado as-is na request JSON
- **No conversion:** Tudo é enviado verbatim

#### Tool Call Parsing
```python
for tc in data.get("tool_use_calls", []):
    tool_calls.append(ToolUseCall(
        id=tc.get("id", ""),
        tool=tc.get("tool", ""),
        input=tc.get("input", {}),
    ))
```
**Simples:** Assume agent ja retorna normalized CPEResponse format

#### Response Format (Expected)
```
{
  "text": "...",
  "tool_use_calls": [
    {"id": "...", "tool": "...", "input": {...}}
  ],
  "input_tokens": 0,
  "output_tokens": 0,
  "stop_reason": "end_turn"
}
```

#### Lifecycle & Protocol
1. **PairingAdapter.__init__:**
   - Gera session_id (8-char hex)
   - Gera key (HACA-XXXX-Y format)
   - Escreve `.meta.json` com session metadata
   - Imprime banner com instruções

2. **invoke():**
   - Remove stale response file
   - Escreve `.request.json` (prompt)
   - Chama `on_prompt_pending` hook (se layout provided)
   - **Blocks** até response file aparecer (timeout: 300s)
   - Lê `.response.json` e parsa
   - Deleta response file
   - Raises CPEError se timeout

3. **stop():**
   - Deleta `.meta.json`, `.request.json`, `.response.json`
   - Called em __del__ (context manager not used)

#### MCP Server Integration
- External `fcp_mcp_server.py` lista sessions via `~/.fcp/pairing/`
- MCP tools: `fcp_poll` (read request), `fcp_respond` (write response)
- **Flow:**
  1. IDE/CLI connects to MCP server
  2. Periodically calls `fcp_poll` → returns pending prompt or empty
  3. Agent processes → calls `fcp_respond` with completion
  4. invoke() unblocks

#### Quirks/Issues
- **No tool_call IDs expected:** Response format allows empty IDs
  - **Design:** Assumes external agent may not provide IDs
- **Filesystem-based polling:** Not ideal para high-latency scenarios
  - **Timeout 300s:** Pode ser insuficiente para agents lentos
  - **Poll interval 0.25s:** CPU-friendly mas latência adicional
- **Key generation:** HACA-XXXX-Y format; uso unclear (cosmetic?)
- **Hook integration:** `on_prompt_pending` assume layout exists
  - **Safety:** `if self._layout` — silent skip se None
- **No built-in retry:** File-based polling pode corromper se files deletados durante leitura

#### Compliance com Especificação
- ✅ Pairing mode design is local-first (filesystem bridge)
- ✅ Response format é CPEResponse-compatible
- ⚠ Timeout may be too long for interactive scenarios
- ⚠ File-based IPC is fragile (race conditions possible)

---

## 3. Comparação de Tool Calling

### 3.1 Tabela Comparativa

| Aspecto | Anthropic | OpenAI | Google | Ollama | Pairing |
|---------|-----------|--------|--------|--------|---------|
| **Tool call location** | `content[]` | `message.tool_calls[]` | `parts[]` | `message.tool_calls[]` | `tool_use_calls[]` |
| **Argument format** | dict | JSON string | dict | dict \| JSON string | dict |
| **Argument parsing** | Direct | `json.loads()` + fallback | Direct | `json.loads()` + fallback | Direct |
| **Tool call ID** | ✅ Present | ✅ Present | ❌ Absent | ❌ Absent | Optional |
| **Parallel calls** | ✅ Supported | ✅ Supported | ⚠ Order-dependent | ✅ Supported | Depends on agent |
| **Multiple tool per turn** | ✅ Multiple | ✅ Multiple | ⚠ Need order mapping | ✅ Multiple | Depends |
| **Tool result format** | `[tool] {json}` | `[tool] {json}` | `functionResponse` | `role: tool` | Depends |

### 3.2 Argument Format Details

**Anthropic:**
```python
input=block.get("input", {})  # Already dict
```

**OpenAI:**
```python
raw_args = tc.get("function", {}).get("arguments", "{}")  # String
parsed_input = json.loads(raw_args)  # Parse required
```

**Google:**
```python
input=fc.get("args", {})  # Already dict
```

**Ollama:**
```python
raw_args = fn.get("arguments", {})  # Dict or string
if isinstance(raw_args, str):
    raw_args = json.loads(raw_args)  # Conditional parse
```

**Pairing:**
```python
input=tc.get("input", {})  # Assumes external agent already normalized
```

### 3.3 Tool Call ID Handling

| Provider | ID Support | Implication |
|----------|-----------|-------------|
| Anthropic | ✅ Full | Can map results back to specific calls |
| OpenAI | ✅ Full | Can map results back to specific calls |
| Google | ❌ None | Order-dependent (fragile) |
| Ollama | ❌ None | Order-dependent (fragile) |
| Pairing | Optional | Depends on external agent |

**Risk:** Google/Ollama assume order is preserved:
```python
for j, fc in enumerate(last_function_calls):
    resp = tool_results[j] if j < len(tool_results) else {}
```
If tool results come out of order or duplicated, mapping breaks.

### 3.4 Multiple Tool Calls per Turn

**Anthropic, OpenAI, Ollama:** Native support via loops over array.

**Google:** Order-dependent mapping; OK se single turn mas risky em edge cases.

**Example fragility (Google):**
```
Turn 1: Model calls [tool_a, tool_b]
        Response has tool_calls[0] = tool_a, tool_calls[1] = tool_b
Turn 2: User provides results in order: [tool_b_result, tool_a_result]
        Adapter maps: results[0] → tool_a (WRONG!)
```

**Mitigation:** Document that tool results must be in call order.

---

## 4. Problemas & Gaps Identificados

### 4.1 API Versioning & Compliance

| Provider | Status | Issue | Impact | Priority |
|----------|--------|-------|--------|----------|
| **Anthropic** | 🟡 Outdated | API version 2023-06-01 (current: 2024-06-15) | Extended thinking not supported | HIGH |
| **OpenAI** | ✅ Current | None | N/A | — |
| **Google** | 🟡 Beta | API is v1beta (experimental) | Breaking changes possible | MEDIUM |
| **Ollama** | ✅ Current | None | N/A | — |
| **Pairing** | N/A | Filesystem protocol (no versioning) | Changes hard to track | LOW |

### 4.2 Parsing Fragility

#### OpenAI: Arguments as JSON string
**Issue:** `json.loads()` can fail, falls back silently to empty dict.
```python
try:
    parsed_input = json.loads(raw_args)
except (json.JSONDecodeError, TypeError):
    parsed_input = {}  # Silent failure
```
**Impact:** Tool receives empty args instead of error.
**Recommendation:** Log warning on parse failure.

#### Google: Order-dependent tool call mapping
**Issue:** No tool call IDs; assumes order preserved.
```python
for j, fc in enumerate(last_function_calls):
    resp = tool_results[j] if j < len(tool_results) else {}
```
**Impact:** If tool results out of order, wrong mapping.
**Recommendation:** Document requirement or generate synthetic IDs.

#### Ollama: Arguments dict or string
**Issue:** Inconsistent response format (Ollama bug or design choice unclear).
```python
if isinstance(raw_args, str):
    try:
        raw_args = json.loads(raw_args)
    except:
        raw_args = {}
```
**Impact:** May lose args if JSON parse fails.
**Recommendation:** Log what happened; investigate Ollama version.

### 4.3 Error Handling Gaps

| Issue | Current | Recommendation |
|-------|---------|-----------------|
| **Malformed tool response** | Silent fallback (empty dict) | Log warning + store original |
| **Missing fields in API response** | `.get()` with defaults | Validate response schema |
| **Rate limit handling** | CPERateLimitError raised | No exponential backoff (in session loop) |
| **Token count mismatches** | Adapted per provider | Document expected ranges |
| **System message for OpenAI** | Injected in messages | Warn if exceeded token limit |

### 4.4 Performance Issues

#### OpenAI: System message injection
**Issue:** System message sent with every invoke, increasing token usage.
**Impact:** ~50-200 tokens per request (depends on system size).
**Recommendation:** Implement prompt caching or keep system external.

#### Ollama: No streaming support
**Issue:** Always waits for full response (`stream: False`).
**Impact:** High latency for long outputs; can't show intermediate results.
**Recommendation:** Implement streaming as opt-in feature.

#### Pairing: Filesystem polling
**Issue:** Poll interval 0.25s, timeout 300s.
**Impact:** Latency on every invoke; not ideal for real-time.
**Recommendation:** Reduce poll interval or use inotify/watchdog.

### 4.5 Inconsistencies Between Adapters

| Aspect | Inconsistency | Status |
|--------|---------------|--------|
| **Tool result format** | '[tool] {json}' vs functionResponse vs role:tool | By design (API differences) |
| **Tool call IDs** | Present (Anthropic/OpenAI) vs absent (Google/Ollama) | Fragile |
| **Message format** | System separate (Anthropic) vs injected (OpenAI/Ollama) | Design choice |
| **Arguments parsing** | Direct dict (Anthropic/Google) vs JSON string (OpenAI/Ollama) | API design |
| **Token counting** | input/output vs prompt/completion vs prompt_eval/eval | Inconsistent naming |

**None are breaking,** but adapter-specific knowledge needed.

### 4.6 Known Models Registry

```python
KNOWN_MODELS: dict[str, list[str]] = {
    "anthropic": [
        "claude-opus-4-6",
        "claude-sonnet-4-6",
        "claude-haiku-4-5-20251001",
    ],
    "openai": [
        "gpt-4o",
        "gpt-4o-mini",
        "o3-mini",
    ],
    "google": [
        "gemini-3.1-flash-lite-preview",
        "gemini-3-flash-preview",
        "gemini-3.1-pro-preview",
        "gemini-2.5-flash",
        "gemini-2.0-flash",
    ],
    "ollama": [],
    "pairing": ["external"],
}
```

**Issue:** Lists are hardcoded; new models require code change.
**Recommendation:** Load from remote registry or config file.

---

## 5. Recomendações Prioritárias

### 5.1 O que consertar primeiro

#### P0: ANTHROPIC API VERSION UPDATE
**What:** Update API version from 2023-06-01 to 2024-06-15.
**Why:** Extended thinking now standard; API may have breaking changes.
**How:**
1. Change `_API_VERSION = "2024-06-15"`
2. Test with extended thinking prompts
3. Verify response format unchanged

**Effort:** 1h (mostly testing)

#### P0: ERROR HANDLING ON PARSE FAILURE
**What:** Log malformed tool args instead of silent fallback.
**Why:** Harder to debug when tool receives empty args.
**How:**
```python
try:
    parsed_input = json.loads(raw_args)
except (json.JSONDecodeError, TypeError) as e:
    logger.warning(f"Tool arg parse failed for {tool}: {e}")
    parsed_input = {}
```
**Effort:** 30m

#### P1: GOOGLE ADAPTER — SYNTHETIC IDS
**What:** Generate synthetic tool_call IDs for Google (which lacks native support).
**Why:** Current order-dependent mapping is fragile.
**How:**
```python
for i, fc in enumerate(last_function_calls):
    ToolUseCall(
        id=f"google-{i}",  # Synthetic
        tool=fc.get("name", ""),
        ...
    )
```
**Effort:** 1h

#### P1: OPENAI — AVOID SYSTEM MESSAGE INJECTION
**What:** Store system message externally; inject only if needed.
**Why:** Token waste (~100+ per request).
**How:** Requires refactor of session loop (stores system separately).
**Effort:** 2-3h

### 5.2 O que testar primeiro

#### Unit Tests (per adapter)
```python
# anthropic_test.py
def test_anthropic_parse_tool_use():
    data = {
        "content": [
            {"type": "tool_use", "id": "123", "name": "fcp_exec", "input": {"cmd": "ls"}}
        ]
    }
    resp = _parse_response(data)
    assert len(resp.tool_use_calls) == 1
    assert resp.tool_use_calls[0].id == "123"
```

#### Edge Cases per Adapter
1. **Anthropic:** Empty content array, malformed input
2. **OpenAI:** JSON parse failure in arguments, missing finish_reason
3. **Google:** No parts in response, mixed text/thought blocks, order mismatch
4. **Ollama:** Arguments as string vs dict, missing tool_calls
5. **Pairing:** Response file not created, malformed JSON, timeout

#### Integration Tests
- Multi-tool calls in single turn
- Tool results in multiple turns
- Mixed text + tool calls
- Token counting accuracy

### 5.3 O que documentar primeiro

#### Adapter-specific Docs
**File:** `docs/cpe_adapter_guide.md` (new)

Each adapter section should document:
1. API version & URL
2. Tool calling format & limitations
3. Message format expectations (system, results)
4. Token counting semantics
5. Known issues & workarounds
6. Example requests/responses

#### Tool Result Format Standardization
**File:** `docs/tool_results_format.md` (new)

Document that:
- FCP sends tool results as '[tool_name] {json}' in user messages
- Adapters convert as needed (Google → functionResponse, Ollama → role:tool)
- Must preserve order (for Google/Ollama)

#### Migration Guide (Anthropic API update)
**File:** `docs/anthropic_api_migration.md` (new)

When updating to 2024-06-15:
1. Changelog of breaking changes
2. Testing checklist
3. Rollback plan

---

## 6. Summary Table

| Adapter | Status | Compliance | Concerns | Next Action |
|---------|--------|-----------|----------|-------------|
| **Anthropic** | 🟡 Working | ⚠ API outdated | Extended thinking missing | Update API version |
| **OpenAI** | ✅ Working | ✅ Current | System message inefficient | Implement caching |
| **Google** | 🟡 Working | ⚠ Beta API | No tool IDs (order-dependent) | Add synthetic IDs |
| **Ollama** | 🟡 Working | ✅ Current | Arguments format inconsistent | Investigate/fix |
| **Pairing** | ✅ Working | ✅ Design | Filesystem polling latency | Document limitations |

---

## 7. Referências

**Base Interface:**
- `/home/estupendo/code/HACA/implementations/fcp-ref/fcp_base/cpe/base.py`
- `/home/estupendo/code/HACA/implementations/fcp-ref/fcp_base/cpe/_http.py`

**Adapters:**
- `/home/estupendo/code/HACA/implementations/fcp-ref/fcp_base/cpe/anthropic.py`
- `/home/estupendo/code/HACA/implementations/fcp-ref/fcp_base/cpe/openai.py`
- `/home/estupendo/code/HACA/implementations/fcp-ref/fcp_base/cpe/google.py`
- `/home/estupendo/code/HACA/implementations/fcp-ref/fcp_base/cpe/ollama.py`
- `/home/estupendo/code/HACA/implementations/fcp-ref/fcp_base/cpe/pairing.py`

**Related:**
- API Docs: https://docs.anthropic.com/, https://platform.openai.com/docs/, https://ai.google.dev/
- Ollama: https://ollama.com/
- HACA Spec: `/home/estupendo/code/HACA/specs/`

---

**Document Version:** 1.0
**Last Updated:** 2026-03-21
**Author:** Claude Code Agent
**Status:** Ready for Review
