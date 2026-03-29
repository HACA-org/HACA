import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { resolveAdapter } from './resolve.js'
import { CPEConfigError } from '../types/cpe.js'

describe('cpe/resolve', () => {
  const savedEnv: Record<string, string | undefined> = {}

  beforeEach(() => {
    savedEnv['ANTHROPIC_API_KEY'] = process.env['ANTHROPIC_API_KEY']
    savedEnv['OPENAI_API_KEY']    = process.env['OPENAI_API_KEY']
    savedEnv['GOOGLE_API_KEY']    = process.env['GOOGLE_API_KEY']
    process.env['ANTHROPIC_API_KEY'] = 'ant-test'
    process.env['OPENAI_API_KEY']    = 'oai-test'
    process.env['GOOGLE_API_KEY']    = 'goog-test'
  })

  afterEach(() => {
    process.env['ANTHROPIC_API_KEY'] = savedEnv['ANTHROPIC_API_KEY']
    process.env['OPENAI_API_KEY']    = savedEnv['OPENAI_API_KEY']
    process.env['GOOGLE_API_KEY']    = savedEnv['GOOGLE_API_KEY']
  })

  it('resolves anthropic adapter', () => {
    const adapter = resolveAdapter('anthropic:claude-opus-4-6')
    expect(adapter.provider).toBe('anthropic')
    expect(adapter.model).toBe('claude-opus-4-6')
  })

  it('resolves openai adapter', () => {
    const adapter = resolveAdapter('openai:gpt-4o')
    expect(adapter.provider).toBe('openai')
    expect(adapter.model).toBe('gpt-4o')
  })

  it('resolves google adapter', () => {
    const adapter = resolveAdapter('google:gemini-2.0-flash')
    expect(adapter.provider).toBe('google')
    expect(adapter.model).toBe('gemini-2.0-flash')
  })

  it('resolves ollama adapter (no key required)', () => {
    const adapter = resolveAdapter('ollama:llama3.2')
    expect(adapter.provider).toBe('ollama')
    expect(adapter.model).toBe('llama3.2')
  })

  it('throws CPEConfigError for "auto" shorthand (removed — use explicit provider:model)', () => {
    expect(() => resolveAdapter('auto')).toThrow(CPEConfigError)
  })

  it('handles model identifiers with colons (ollama tag format)', () => {
    const adapter = resolveAdapter('ollama:llama3.2:latest')
    expect(adapter.model).toBe('llama3.2:latest')
  })

  it('throws CPEConfigError on missing colon', () => {
    expect(() => resolveAdapter('anthropic')).toThrow(CPEConfigError)
  })

  it('throws CPEConfigError on empty provider', () => {
    expect(() => resolveAdapter(':model')).toThrow(CPEConfigError)
  })

  it('throws CPEConfigError on unknown provider', () => {
    expect(() => resolveAdapter('cohere:command')).toThrow(CPEConfigError)
  })

  it('throws CPEConfigError when ANTHROPIC_API_KEY is absent', () => {
    delete process.env['ANTHROPIC_API_KEY']
    expect(() => resolveAdapter('anthropic:claude-opus-4-6')).toThrow(CPEConfigError)
  })

  it('throws CPEConfigError when OPENAI_API_KEY is absent', () => {
    delete process.env['OPENAI_API_KEY']
    expect(() => resolveAdapter('openai:gpt-4o')).toThrow(CPEConfigError)
  })
})
