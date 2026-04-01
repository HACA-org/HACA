import { describe, it, expect } from 'vitest'
import { normalizeAnthropic, normalizeOpenAI, normalizeGoogle, normalizeOllama } from './normalize.js'
import { CPEInvokeError } from '../types/cpe.js'

describe('cpe/normalize', () => {
  describe('normalizeAnthropic', () => {
    it('extracts text content', () => {
      const raw = {
        content: [{ type: 'text', text: 'hello world' }],
        stop_reason: 'end_turn',
        usage: { input_tokens: 100, output_tokens: 20 },
      }
      const resp = normalizeAnthropic(raw)
      expect(resp.content).toBe('hello world')
      expect(resp.toolUses).toHaveLength(0)
      expect(resp.stopReason).toBe('end_turn')
      expect(resp.usage).toEqual({ inputTokens: 100, outputTokens: 20 })
    })

    it('extracts tool_use blocks', () => {
      const raw = {
        content: [
          { type: 'text', text: 'calling tool' },
          { type: 'tool_use', id: 'tu_1', name: 'fcp_exec', input: { action: 'x' } },
        ],
        stop_reason: 'tool_use',
        usage: { input_tokens: 200, output_tokens: 50 },
      }
      const resp = normalizeAnthropic(raw)
      expect(resp.stopReason).toBe('tool_use')
      expect(resp.toolUses).toHaveLength(1)
      expect(resp.toolUses[0]?.name).toBe('fcp_exec')
      expect(resp.toolUses[0]?.id).toBe('tu_1')
    })

    it('maps max_tokens stop reason', () => {
      const raw = {
        content: [],
        stop_reason: 'max_tokens',
        usage: { input_tokens: 0, output_tokens: 0 },
      }
      expect(normalizeAnthropic(raw).stopReason).toBe('max_tokens')
    })

    it('throws CPEInvokeError on non-object input', () => {
      expect(() => normalizeAnthropic('string')).toThrow(CPEInvokeError)
      expect(() => normalizeAnthropic(null)).toThrow(CPEInvokeError)
    })

    it('throws CPEInvokeError when content is not an array', () => {
      expect(() => normalizeAnthropic({ content: 'bad', stop_reason: 'end_turn', usage: {} }))
        .toThrow(CPEInvokeError)
    })
  })

  describe('normalizeOpenAI', () => {
    it('extracts text content', () => {
      const raw = {
        choices: [{ message: { role: 'assistant', content: 'hi' }, finish_reason: 'stop' }],
        usage: { prompt_tokens: 50, completion_tokens: 10 },
      }
      const resp = normalizeOpenAI(raw)
      expect(resp.content).toBe('hi')
      expect(resp.stopReason).toBe('end_turn')
      expect(resp.usage.inputTokens).toBe(50)
    })

    it('extracts tool_calls', () => {
      const raw = {
        choices: [{
          message: {
            content: null,
            tool_calls: [{
              id: 'call_1', type: 'function',
              function: { name: 'fcp_exec', arguments: '{"action":"x"}' },
            }],
          },
          finish_reason: 'tool_calls',
        }],
        usage: { prompt_tokens: 100, completion_tokens: 30 },
      }
      const resp = normalizeOpenAI(raw)
      expect(resp.stopReason).toBe('tool_use')
      expect(resp.toolUses).toHaveLength(1)
      expect(resp.toolUses[0]?.name).toBe('fcp_exec')
      expect(resp.toolUses[0]?.input).toEqual({ action: 'x' })
    })

    it('throws CPEInvokeError on malformed tool arguments JSON', () => {
      const raw = {
        choices: [{
          message: {
            content: null,
            tool_calls: [{ id: 'call_1', type: 'function', function: { name: 'fcp_exec', arguments: '{bad json' } }],
          },
          finish_reason: 'tool_calls',
        }],
        usage: { prompt_tokens: 10, completion_tokens: 5 },
      }
      expect(() => normalizeOpenAI(raw)).toThrow(CPEInvokeError)
    })

    it('throws on empty choices', () => {
      expect(() => normalizeOpenAI({ choices: [], usage: {} })).toThrow(CPEInvokeError)
    })
  })

  describe('normalizeGoogle', () => {
    it('extracts text content', () => {
      const raw = {
        candidates: [{
          content: { role: 'model', parts: [{ text: 'gemini response' }] },
          finishReason: 'STOP',
        }],
        usageMetadata: { promptTokenCount: 80, candidatesTokenCount: 15 },
      }
      const resp = normalizeGoogle(raw)
      expect(resp.content).toBe('gemini response')
      expect(resp.stopReason).toBe('end_turn')
      expect(resp.usage.inputTokens).toBe(80)
    })

    it('extracts functionCall parts', () => {
      const raw = {
        candidates: [{
          content: {
            role: 'model',
            parts: [{ functionCall: { name: 'fcp_exec', args: { action: 'y' } } }],
          },
          finishReason: 'STOP',
        }],
        usageMetadata: {},
      }
      const resp = normalizeGoogle(raw)
      expect(resp.toolUses).toHaveLength(1)
      expect(resp.toolUses[0]?.name).toBe('fcp_exec')
    })

    it('uses function name in tool_use id', () => {
      const raw = {
        candidates: [{
          content: {
            role: 'model',
            parts: [
              { functionCall: { name: 'tool_a', args: {} } },
              { functionCall: { name: 'tool_b', args: {} } },
            ],
          },
          finishReason: 'STOP',
        }],
        usageMetadata: {},
      }
      const resp = normalizeGoogle(raw)
      expect(resp.toolUses[0]?.id).toBe('gcall_tool_a_0')
      expect(resp.toolUses[1]?.id).toBe('gcall_tool_b_1')
    })

    it('maps SAFETY and OTHER finishReason to end_turn', () => {
      for (const finishReason of ['SAFETY', 'OTHER', 'RECITATION']) {
        const raw = {
          candidates: [{ content: { role: 'model', parts: [{ text: 'hi' }] }, finishReason }],
          usageMetadata: {},
        }
        expect(normalizeGoogle(raw).stopReason).toBe('end_turn')
      }
    })

    it('maps MAX_TOKENS finishReason to max_tokens', () => {
      const raw = {
        candidates: [{ content: { role: 'model', parts: [] }, finishReason: 'MAX_TOKENS' }],
        usageMetadata: {},
      }
      expect(normalizeGoogle(raw).stopReason).toBe('max_tokens')
    })

    it('returns tool_use stopReason when tool calls present', () => {
      const raw = {
        candidates: [{
          content: {
            role: 'model',
            parts: [{ functionCall: { name: 'fcp_exec', args: {} } }],
          },
          finishReason: 'STOP',
        }],
        usageMetadata: {},
      }
      expect(normalizeGoogle(raw).stopReason).toBe('tool_use')
    })

    it('throws on empty candidates', () => {
      expect(() => normalizeGoogle({ candidates: [] })).toThrow(CPEInvokeError)
    })
  })

  describe('normalizeOllama', () => {
    it('extracts text content', () => {
      const raw = {
        model: 'llama3.2',
        message: { role: 'assistant', content: 'ollama response' },
        done_reason: 'stop',
        done: true,
      }
      const resp = normalizeOllama(raw)
      expect(resp.content).toBe('ollama response')
      expect(resp.stopReason).toBe('end_turn')
    })

    it('extracts tool_calls', () => {
      const raw = {
        message: {
          content: '',
          tool_calls: [{ function: { name: 'fcp_exec', arguments: { action: 'z' } } }],
        },
        done_reason: 'stop',
        done: true,
      }
      const resp = normalizeOllama(raw)
      expect(resp.stopReason).toBe('tool_use')
      expect(resp.toolUses).toHaveLength(1)
      expect(resp.toolUses[0]?.name).toBe('fcp_exec')
    })

    it('uses deterministic index-based tool_use ids', () => {
      const raw = {
        message: {
          content: '',
          tool_calls: [
            { function: { name: 'tool_a', arguments: {} } },
            { function: { name: 'tool_b', arguments: {} } },
          ],
        },
        done_reason: 'stop',
        done: true,
      }
      const resp = normalizeOllama(raw)
      expect(resp.toolUses[0]?.id).toBe('ollama_tool_a_0')
      expect(resp.toolUses[1]?.id).toBe('ollama_tool_b_1')
    })

    it('throws on missing message field', () => {
      expect(() => normalizeOllama({ done: true })).toThrow(CPEInvokeError)
    })
  })
})
