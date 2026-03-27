// Raw API response → CPEResponse. One function per provider, no I/O.

import type { CPEResponse, StopReason, ToolUseBlock, CPEUsage } from '../types/cpe.js'
import { CPEInvokeError } from '../types/cpe.js'

function toRecord(val: unknown, ctx: string): Record<string, unknown> {
  if (typeof val !== 'object' || val === null || Array.isArray(val)) {
    throw new CPEInvokeError(`${ctx}: expected object, got ${Array.isArray(val) ? 'array' : typeof val}`)
  }
  return val as Record<string, unknown>
}

function toArray(val: unknown, ctx: string): unknown[] {
  if (!Array.isArray(val)) throw new CPEInvokeError(`${ctx}: expected array, got ${typeof val}`)
  return val
}

const anthropicStopMap: Record<string, StopReason> = {
  tool_use:      'tool_use',
  end_turn:      'end_turn',
  max_tokens:    'max_tokens',
  stop_sequence: 'stop_sequence',
}

export function normalizeAnthropic(raw: unknown): CPEResponse {
  const r = toRecord(raw, 'Anthropic response')
  const content = toArray(r['content'], 'content')

  const text = content
    .filter((b): b is { type: 'text'; text: string } =>
      typeof b === 'object' && b !== null && (b as Record<string, unknown>)['type'] === 'text'
    )
    .map(b => b.text)
    .join('')

  const toolUses: ToolUseBlock[] = content
    .filter((b): b is { type: 'tool_use'; id: string; name: string; input: unknown } =>
      typeof b === 'object' && b !== null && (b as Record<string, unknown>)['type'] === 'tool_use'
    )
    .map(b => ({ type: 'tool_use' as const, id: b.id, name: b.name, input: b.input }))

  const u = toRecord(r['usage'], 'usage')
  const usage: CPEUsage = {
    inputTokens:  Number(u['input_tokens'])  || 0,
    outputTokens: Number(u['output_tokens']) || 0,
  }

  return {
    stopReason: anthropicStopMap[String(r['stop_reason'])] ?? 'end_turn',
    content: text,
    toolUses,
    usage,
  }
}

const openaiStopMap: Record<string, StopReason> = {
  tool_calls: 'tool_use',
  stop:       'end_turn',
  length:     'max_tokens',
}

export function normalizeOpenAI(raw: unknown): CPEResponse {
  const r = toRecord(raw, 'OpenAI response')
  const choices = toArray(r['choices'], 'choices')
  if (choices.length === 0) throw new CPEInvokeError('OpenAI response: empty choices')

  const choice  = toRecord(choices[0], 'choices[0]')
  const message = toRecord(choice['message'], 'message')
  const content = typeof message['content'] === 'string' ? message['content'] : ''

  const rawCalls = message['tool_calls']
  const toolUses: ToolUseBlock[] = rawCalls != null
    ? toArray(rawCalls, 'tool_calls').map(tc => {
        const c  = toRecord(tc, 'tool_call')
        const fn = toRecord(c['function'], 'function')
        return {
          type:  'tool_use' as const,
          id:    String(c['id']),
          name:  String(fn['name']),
          input: JSON.parse(String(fn['arguments'])) as unknown,
        }
      })
    : []

  const u = toRecord(r['usage'], 'usage')
  return {
    stopReason: openaiStopMap[String(choice['finish_reason'])] ?? 'end_turn',
    content,
    toolUses,
    usage: {
      inputTokens:  Number(u['prompt_tokens'])     || 0,
      outputTokens: Number(u['completion_tokens']) || 0,
    },
  }
}

export function normalizeGoogle(raw: unknown): CPEResponse {
  const r = toRecord(raw, 'Gemini response')
  const candidates = toArray(r['candidates'], 'candidates')
  if (candidates.length === 0) throw new CPEInvokeError('Gemini response: empty candidates')

  const candidate = toRecord(candidates[0], 'candidates[0]')
  const gcontent  = toRecord(candidate['content'], 'content')
  const parts     = toArray(gcontent['parts'], 'parts')

  const text = parts
    .filter((p): p is { text: string } =>
      typeof p === 'object' && p !== null && typeof (p as Record<string, unknown>)['text'] === 'string'
    )
    .map(p => p.text)
    .join('')

  const toolUses: ToolUseBlock[] = parts
    .filter((p): p is { functionCall: { name: string; args: unknown } } =>
      typeof p === 'object' && p !== null &&
      typeof (p as Record<string, unknown>)['functionCall'] === 'object'
    )
    .map((p, i) => ({
      type:  'tool_use' as const,
      id:    `gcall_${i}`,
      name:  p.functionCall.name,
      input: p.functionCall.args,
    }))

  const meta   = r['usageMetadata']
  const uMeta  = typeof meta === 'object' && meta !== null ? meta as Record<string, unknown> : {}
  const finish = String((candidate as Record<string, unknown>)['finishReason'] ?? 'STOP')

  return {
    stopReason: finish === 'MAX_TOKENS' ? 'max_tokens' : 'end_turn',
    content: text,
    toolUses,
    usage: {
      inputTokens:  Number(uMeta['promptTokenCount'])     || 0,
      outputTokens: Number(uMeta['candidatesTokenCount']) || 0,
    },
  }
}

export function normalizeOllama(raw: unknown): CPEResponse {
  const r       = toRecord(raw, 'Ollama response')
  const message = toRecord(r['message'], 'message')
  const content = typeof message['content'] === 'string' ? message['content'] : ''

  const rawCalls = message['tool_calls']
  const toolUses: ToolUseBlock[] = rawCalls != null
    ? toArray(rawCalls, 'tool_calls').map(tc => {
        const c  = toRecord(tc, 'tool_call')
        const fn = toRecord(c['function'], 'function')
        return {
          type:  'tool_use' as const,
          id:    `ollama_${String(fn['name'])}_${Date.now()}`,
          name:  String(fn['name']),
          input: fn['arguments'] ?? {},
        }
      })
    : []

  const doneReason = String(r['done_reason'] ?? 'stop')
  return {
    stopReason: doneReason === 'length' ? 'max_tokens'
      : toolUses.length > 0 ? 'tool_use' : 'end_turn',
    content,
    toolUses,
    usage: { inputTokens: 0, outputTokens: 0 },
  }
}
