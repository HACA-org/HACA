import type { CPEAdapter, CPERequest, CPEResponse, CPEMessage, TextBlock, ToolUseBlock, ToolResultBlock } from '../types/cpe.js'
import { CPEInvokeError } from '../types/cpe.js'
import { normalizeOllama } from './normalize.js'

const DEFAULT_BASE = 'http://localhost:11434'

// Convert internal CPEMessage history to Ollama's OpenAI-compatible format.
// Tool calls and tool results must be preserved — without them the model loses
// track of what it called and re-calls the same tools indefinitely.
function toOllamaMessages(messages: CPEMessage[]): unknown[] {
  const out: unknown[] = []
  for (const msg of messages) {
    if (typeof msg.content === 'string') {
      out.push({ role: msg.role, content: msg.content })
      continue
    }
    const blocks = msg.content
    const toolResults = blocks.filter((b): b is ToolResultBlock => b.type === 'tool_result')
    if (toolResults.length > 0) {
      // Ollama: tool results are role:'tool' messages (one per result)
      for (const tr of toolResults) {
        out.push({ role: 'tool', tool_call_id: tr.tool_use_id, content: tr.content })
      }
      continue
    }
    const text     = blocks.filter((b): b is TextBlock    => b.type === 'text').map(b => b.text).join('')
    const toolUses = blocks.filter((b): b is ToolUseBlock => b.type === 'tool_use')
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

// Ollama uses an OpenAI-compatible chat API but with streaming on by default.
// We force stream:false and pass tools in the OpenAI function-calling schema.
// Context window varies by model; 128k is a safe conservative default.
export function createOllamaAdapter(model: string, baseUrl: string = DEFAULT_BASE): CPEAdapter {
  return {
    provider:      'ollama',
    model,
    contextWindow: 128000,

    async invoke(req: CPERequest): Promise<CPEResponse> {
      const body = {
        model,
        stream: false,
        messages: [
          ...(req.system !== undefined ? [{ role: 'system', content: req.system }] : []),
          ...toOllamaMessages(req.messages),
        ],
        ...(req.tools.length > 0 ? {
          tools: req.tools.map(t => ({
            type:     'function',
            function: { name: t.name, description: t.description, parameters: t.input_schema },
          })),
        } : {}),
      }
      const resp = await fetch(`${baseUrl}/api/chat`, {
        method:  'POST',
        headers: { 'content-type': 'application/json' },
        body:    JSON.stringify(body),
      })
      if (!resp.ok) throw new CPEInvokeError(`Ollama API error ${resp.status}: ${resp.statusText}`, resp.status)
      return normalizeOllama(await resp.json() as unknown)
    },
  }
}
