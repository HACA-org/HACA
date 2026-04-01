import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { createAnthropicAdapter } from './anthropic.js'
import { createOpenAIAdapter }    from './openai.js'
import { createGoogleAdapter }    from './google.js'
import { createOllamaAdapter }    from './ollama.js'
import { resolveAdapter }         from './resolve.js'
import { CPEInvokeError, CPEConfigError } from '../types/cpe.js'
import type { CPERequest }        from '../types/cpe.js'

const minReq: CPERequest = {
  messages: [{ role: 'user', content: 'hello' }],
  tools: [],
}

function mockFetch(body: unknown, status = 200): void {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok:     status >= 200 && status < 300,
    status,
    statusText: status === 200 ? 'OK' : 'Error',
    json:   () => Promise.resolve(body),
  }))
}

afterEach(() => { vi.unstubAllGlobals() })

// --- Anthropic ---
describe('AnthropicAdapter', () => {
  const anthropicResp = {
    content:     [{ type: 'text', text: 'hello back' }],
    stop_reason: 'end_turn',
    usage:       { input_tokens: 10, output_tokens: 5 },
  }

  it('returns CPEResponse on success', async () => {
    mockFetch(anthropicResp)
    const adapter = createAnthropicAdapter('claude-sonnet-4-6', 'key')
    const resp = await adapter.invoke(minReq)
    expect(resp.content).toBe('hello back')
    expect(resp.usage.inputTokens).toBe(10)
  })

  it('sends correct headers', async () => {
    mockFetch(anthropicResp)
    const adapter = createAnthropicAdapter('claude-sonnet-4-6', 'my-key')
    await adapter.invoke(minReq)
    const [, init] = (vi.mocked(fetch).mock.calls[0] ?? []) as [string, RequestInit]
    const headers = init.headers as Record<string, string>
    expect(headers['x-api-key']).toBe('my-key')
    expect(headers['anthropic-version']).toBeDefined()
  })

  it('throws CPEInvokeError on non-2xx', async () => {
    mockFetch({}, 429)
    await expect(createAnthropicAdapter('claude-sonnet-4-6', 'key').invoke(minReq))
      .rejects.toBeInstanceOf(CPEInvokeError)
  })

  it('exposes correct provider and contextWindow', () => {
    const adapter = createAnthropicAdapter('claude-opus-4-6', 'key')
    expect(adapter.provider).toBe('anthropic')
    expect(adapter.contextWindow).toBe(200000)
  })
})

// --- OpenAI ---
describe('OpenAIAdapter', () => {
  const openaiResp = {
    choices: [{ message: { content: 'hi from openai' }, finish_reason: 'stop' }],
    usage:   { prompt_tokens: 20, completion_tokens: 8 },
  }

  it('returns CPEResponse on success', async () => {
    mockFetch(openaiResp)
    const resp = await createOpenAIAdapter('gpt-4o', 'key').invoke(minReq)
    expect(resp.content).toBe('hi from openai')
    expect(resp.stopReason).toBe('end_turn')
  })

  it('sends Bearer token', async () => {
    mockFetch(openaiResp)
    await createOpenAIAdapter('gpt-4o', 'sk-test').invoke(minReq)
    const [, init] = (vi.mocked(fetch).mock.calls[0] ?? []) as [string, RequestInit]
    const headers = init.headers as Record<string, string>
    expect(headers['authorization']).toBe('Bearer sk-test')
  })

  it('throws CPEInvokeError on non-2xx', async () => {
    mockFetch({}, 500)
    await expect(createOpenAIAdapter('gpt-4o', 'key').invoke(minReq))
      .rejects.toBeInstanceOf(CPEInvokeError)
  })

  it('injects system as first message', async () => {
    mockFetch(openaiResp)
    const req: CPERequest = { ...minReq, system: 'you are helpful' }
    await createOpenAIAdapter('gpt-4o', 'key').invoke(req)
    const [, init] = (vi.mocked(fetch).mock.calls[0] ?? []) as [string, RequestInit]
    const body = JSON.parse(init.body as string) as { messages: Array<{ role: string; content: string }> }
    expect(body.messages[0]).toEqual({ role: 'system', content: 'you are helpful' })
  })
})

// --- Google ---
describe('GoogleAdapter', () => {
  const googleResp = {
    candidates: [{ content: { role: 'model', parts: [{ text: 'gemini here' }] }, finishReason: 'STOP' }],
    usageMetadata: { promptTokenCount: 30, candidatesTokenCount: 12 },
  }

  it('returns CPEResponse on success', async () => {
    mockFetch(googleResp)
    const resp = await createGoogleAdapter('gemini-2.0-flash', 'key').invoke(minReq)
    expect(resp.content).toBe('gemini here')
    expect(resp.usage.inputTokens).toBe(30)
  })

  it('sends api key in x-goog-api-key header', async () => {
    mockFetch(googleResp)
    await createGoogleAdapter('gemini-2.0-flash', 'my-gkey').invoke(minReq)
    const [url, init] = vi.mocked(fetch).mock.calls[0] as [string, RequestInit]
    const headers = init.headers as Record<string, string>
    expect(headers['x-goog-api-key']).toBe('my-gkey')
    expect(url).not.toContain('key=')
  })

  it('throws CPEInvokeError on non-2xx', async () => {
    mockFetch({}, 403)
    await expect(createGoogleAdapter('gemini-2.0-flash', 'key').invoke(minReq))
      .rejects.toBeInstanceOf(CPEInvokeError)
  })
})

// --- resolveAdapter wrapper ---
describe('resolveAdapter (error wrapping)', () => {
  beforeEach(() => {
    process.env['ANTHROPIC_API_KEY'] = 'test-key'
  })
  afterEach(() => {
    delete process.env['ANTHROPIC_API_KEY']
    vi.unstubAllGlobals()
  })

  it('wraps TypeError (network error) as CPEInvokeError', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('fetch failed')))
    const adapter = resolveAdapter('anthropic:claude-sonnet-4-6')
    await expect(adapter.invoke(minReq)).rejects.toBeInstanceOf(CPEInvokeError)
  })

  it('wraps SyntaxError (malformed JSON) as CPEInvokeError', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true, status: 200, statusText: 'OK',
      json: () => Promise.reject(new SyntaxError('bad json')),
    }))
    const adapter = resolveAdapter('anthropic:claude-sonnet-4-6')
    await expect(adapter.invoke(minReq)).rejects.toBeInstanceOf(CPEInvokeError)
  })

  it('passes CPEInvokeError through unchanged', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false, status: 429, statusText: 'Too Many Requests',
      json: () => Promise.resolve({}),
    }))
    const adapter = resolveAdapter('anthropic:claude-sonnet-4-6')
    const err = await adapter.invoke(minReq).catch(e => e)
    expect(err).toBeInstanceOf(CPEInvokeError)
    expect((err as CPEInvokeError).statusCode).toBe(429)
  })

  it('throws CPEConfigError for unknown provider', () => {
    expect(() => resolveAdapter('unknown:model')).toThrow(CPEConfigError)
  })
})

// --- Ollama ---
describe('OllamaAdapter', () => {
  const ollamaResp = {
    message: { role: 'assistant', content: 'ollama reply' },
    done_reason: 'stop',
    done: true,
  }

  it('returns CPEResponse on success', async () => {
    mockFetch(ollamaResp)
    const resp = await createOllamaAdapter('llama3.2').invoke(minReq)
    expect(resp.content).toBe('ollama reply')
  })

  it('uses custom base URL when provided', async () => {
    mockFetch(ollamaResp)
    await createOllamaAdapter('llama3.2', 'http://myhost:11434').invoke(minReq)
    const [url] = vi.mocked(fetch).mock.calls[0] as [string]
    expect(url).toContain('myhost:11434')
  })

  it('forces stream:false in body', async () => {
    mockFetch(ollamaResp)
    await createOllamaAdapter('llama3.2').invoke(minReq)
    const [, init] = vi.mocked(fetch).mock.calls[0] as [string, RequestInit]
    const body = JSON.parse(init.body as string) as { stream: boolean }
    expect(body.stream).toBe(false)
  })
})
