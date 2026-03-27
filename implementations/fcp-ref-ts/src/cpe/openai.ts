import type { CPEAdapter, CPERequest, CPEResponse, CPEMessage, ContentBlock, ToolUseBlock, ToolResultBlock, TextBlock } from '../types/cpe.js'
import { CPEInvokeError } from '../types/cpe.js'
import { normalizeOpenAI } from './normalize.js'

const CONTEXT: Record<string, number> = {
  'gpt-4o':      128000,
  'gpt-4o-mini': 128000,
  'gpt-4-turbo': 128000,
  'o1':          200000,
  'o3-mini':     200000,
}

const API_URL = 'https://api.openai.com/v1/chat/completions'

// Our internal format is Anthropic-style (ContentBlock[]).
// OpenAI expects: tool results as standalone role:'tool' messages,
// and tool uses as `tool_calls` on an assistant message.
function toOpenAIMessages(messages: CPEMessage[]): unknown[] {
  const out: unknown[] = []
  for (const msg of messages) {
    if (typeof msg.content === 'string') {
      out.push({ role: msg.role, content: msg.content })
      continue
    }
    const blocks: ContentBlock[] = msg.content
    const toolResults = blocks.filter((b): b is ToolResultBlock => b.type === 'tool_result')
    if (toolResults.length > 0) {
      for (const tr of toolResults) {
        out.push({ role: 'tool', tool_call_id: tr.tool_use_id, content: tr.content })
      }
      continue
    }
    const text     = blocks.filter((b): b is TextBlock     => b.type === 'text').map(b => b.text).join('')
    const toolUses = blocks.filter((b): b is ToolUseBlock  => b.type === 'tool_use')
    out.push({
      role:    msg.role,
      content: text,
      ...(toolUses.length > 0 ? {
        tool_calls: toolUses.map(tu => ({
          id:       tu.id,
          type:     'function',
          function: { name: tu.name, arguments: JSON.stringify(tu.input) },
        })),
      } : {}),
    })
  }
  return out
}

export function createOpenAIAdapter(model: string, apiKey: string): CPEAdapter {
  return {
    provider:      'openai',
    model,
    contextWindow: CONTEXT[model] ?? 128000,

    async invoke(req: CPERequest): Promise<CPEResponse> {
      const body = {
        model,
        messages: [
          ...(req.system !== undefined ? [{ role: 'system', content: req.system }] : []),
          ...toOpenAIMessages(req.messages),
        ],
        tools: req.tools.map(t => ({
          type:     'function',
          function: { name: t.name, description: t.description, parameters: t.input_schema },
        })),
      }
      const resp = await fetch(API_URL, {
        method:  'POST',
        headers: { 'content-type': 'application/json', 'authorization': `Bearer ${apiKey}` },
        body:    JSON.stringify(body),
      })
      if (!resp.ok) throw new CPEInvokeError(`OpenAI API error ${resp.status}: ${resp.statusText}`, resp.status)
      return normalizeOpenAI(await resp.json() as unknown)
    },
  }
}
