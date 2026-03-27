import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { createCPE, resolveAdapter, createPairingAdapter, detectAvailableModels } from './cpe.js'
import type { CPERequest } from './types.js'

const mockRequest: CPERequest = {
  system: 'You are a helpful assistant.',
  messages: [{ role: 'user', content: 'Hello' }],
}

describe('resolveAdapter', () => {
  it('throws on unknown provider', () => {
    expect(() => resolveAdapter({ provider: 'unknown', model: 'x', profile: 'haca-core' }))
      .toThrow('Unknown CPE provider: unknown')
  })

  it('returns adapter for each known provider', () => {
    for (const provider of ['ollama', 'anthropic', 'google', 'openai']) {
      const adapter = resolveAdapter({ provider, model: 'test', profile: 'haca-core' })
      expect(adapter.provider).toBe(provider)
    }
  })
})

describe('createPairingAdapter', () => {
  it('throws for haca-core profile', () => {
    expect(() => createPairingAdapter({ provider: 'anthropic', model: 'x', profile: 'haca-core' }, 'haca-core'))
      .toThrow('Pairing is not available for haca-core profile')
  })

  it('returns adapter for haca-evolve profile', () => {
    const adapter = createPairingAdapter({ provider: 'ollama', model: 'llama3', profile: 'haca-evolve' }, 'haca-evolve')
    expect(adapter.provider).toBe('ollama')
  })
})

describe('createCPE — profile enforcement', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        message: { content: 'Hello!' },
        done: true,
        prompt_eval_count: 10,
        eval_count: 5,
      }),
    }))
  })

  afterEach(() => vi.unstubAllGlobals())

  it('haca-core forces topology to transparent', async () => {
    const cpe = createCPE({ provider: 'ollama', model: 'llama3', profile: 'haca-core' })
    await cpe.invoke({ ...mockRequest, topology: 'opaque' })
    const body = JSON.parse((vi.mocked(fetch).mock.calls[0]![1] as RequestInit).body as string)
    // opaque was overridden — no tools sent even if provided
    expect(body.tools).toBeUndefined()
  })

  it('haca-evolve preserves requested topology', async () => {
    const cpe = createCPE({ provider: 'ollama', model: 'llama3', profile: 'haca-evolve' })
    const res = await cpe.invoke({ ...mockRequest, topology: 'opaque' })
    expect(res.stopReason).toBe('end_turn')
  })
})

describe('Anthropic adapter', () => {
  beforeEach(() => {
    process.env['ANTHROPIC_API_KEY'] = 'test-key'
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        content: [{ type: 'text', text: 'Hello!' }],
        stop_reason: 'end_turn',
        usage: { input_tokens: 10, output_tokens: 5 },
      }),
    }))
  })

  afterEach(() => {
    delete process.env['ANTHROPIC_API_KEY']
    vi.unstubAllGlobals()
  })

  it('maps response to CPEResponse', async () => {
    const adapter = resolveAdapter({ provider: 'anthropic', model: 'claude-sonnet-4-6', profile: 'haca-core' })
    const res = await adapter.invoke(mockRequest)
    expect(res.content).toBe('Hello!')
    expect(res.usage.inputTokens).toBe(10)
    expect(res.stopReason).toBe('end_turn')
  })

  it('maps tool_use stop reason', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        content: [{ type: 'tool_use', id: 't1', name: 'shell_run', input: { cmd: 'ls' } }],
        stop_reason: 'tool_use',
        usage: { input_tokens: 10, output_tokens: 5 },
      }),
    }))
    const adapter = resolveAdapter({ provider: 'anthropic', model: 'claude-sonnet-4-6', profile: 'haca-evolve' })
    const res = await adapter.invoke(mockRequest)
    expect(res.stopReason).toBe('tool_use')
    expect(res.toolCalls[0]?.name).toBe('shell_run')
  })

  it('throws on API error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 401, text: async () => 'Unauthorized' }))
    const adapter = resolveAdapter({ provider: 'anthropic', model: 'claude-sonnet-4-6', profile: 'haca-core' })
    await expect(adapter.invoke(mockRequest)).rejects.toThrow('Anthropic error: 401')
  })

  it('strips tools in opaque topology', async () => {
    const adapter = resolveAdapter({ provider: 'anthropic', model: 'claude-sonnet-4-6', profile: 'haca-core' })
    await adapter.invoke({
      ...mockRequest,
      topology: 'opaque',
      tools: [{ name: 'shell_run', description: 'run shell', input_schema: {} }],
    })
    const body = JSON.parse((vi.mocked(fetch).mock.calls[0]![1] as RequestInit).body as string)
    expect(body.tools).toBeUndefined()
  })
})

describe('Ollama adapter', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        message: { content: 'Hi!' },
        done: true,
        prompt_eval_count: 8,
        eval_count: 4,
      }),
    }))
  })

  afterEach(() => vi.unstubAllGlobals())

  it('maps response to CPEResponse', async () => {
    const adapter = resolveAdapter({ provider: 'ollama', model: 'llama3', profile: 'haca-core' })
    const res = await adapter.invoke(mockRequest)
    expect(res.content).toBe('Hi!')
    expect(res.toolCalls).toEqual([])
    expect(res.usage.inputTokens).toBe(8)
  })
})

describe('detectAvailableModels', () => {
  afterEach(() => {
    delete process.env['ANTHROPIC_API_KEY']
    delete process.env['GOOGLE_API_KEY']
    delete process.env['OPENAI_API_KEY']
    vi.unstubAllGlobals()
  })

  it('includes anthropic models when key is set', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('no ollama')))
    process.env['ANTHROPIC_API_KEY'] = 'test'
    const models = await detectAvailableModels()
    expect(models.some(m => m.provider === 'anthropic')).toBe(true)
  })

  it('returns empty list when no providers available', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('no ollama')))
    const models = await detectAvailableModels()
    expect(models.filter(m => m.provider !== 'ollama')).toHaveLength(0)
  })
})
