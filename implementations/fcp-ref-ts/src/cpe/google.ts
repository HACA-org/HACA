import type { CPEAdapter, CPERequest, CPEResponse } from '../types/cpe.js'
import { CPEInvokeError } from '../types/cpe.js'
import { normalizeGoogle } from './normalize.js'

const CONTEXT: Record<string, number> = {
  'gemini-2.0-flash': 1000000,
  'gemini-1.5-pro':   2000000,
  'gemini-1.5-flash': 1000000,
}

const BASE = 'https://generativelanguage.googleapis.com/v1beta/models'

// Gemini uses a different schema: 'model' role (not 'assistant'), parts instead of content,
// and functionDeclarations inside a tools wrapper.
function toGeminiBody(req: CPERequest): unknown {
  return {
    contents: req.messages.map(msg => ({
      role: msg.role === 'assistant' ? 'model' : 'user',
      parts: typeof msg.content === 'string'
        ? [{ text: msg.content }]
        : msg.content.map(block => {
            if (block.type === 'text')
              return { text: block.text }
            if (block.type === 'tool_use')
              return { functionCall: { name: block.name, args: block.input } }
            // tool_result: Gemini expects functionResponse with name + response
            return { functionResponse: { name: block.tool_use_id, response: { content: block.content } } }
          }),
    })),
    ...(req.tools.length > 0 ? {
      tools: [{
        functionDeclarations: req.tools.map(t => ({
          name:        t.name,
          description: t.description,
          parameters:  t.input_schema,
        })),
      }],
    } : {}),
    ...(req.system !== undefined ? { systemInstruction: { parts: [{ text: req.system }] } } : {}),
  }
}

export function createGoogleAdapter(model: string, apiKey: string): CPEAdapter {
  return {
    provider:      'google',
    model,
    contextWindow: CONTEXT[model] ?? 1000000,

    async invoke(req: CPERequest): Promise<CPEResponse> {
      const url  = `${BASE}/${model}:generateContent?key=${apiKey}`
      const resp = await fetch(url, {
        method:  'POST',
        headers: { 'content-type': 'application/json' },
        body:    JSON.stringify(toGeminiBody(req)),
      })
      if (!resp.ok) throw new CPEInvokeError(`Google API error ${resp.status}: ${resp.statusText}`, resp.status)
      return normalizeGoogle(await resp.json() as unknown)
    },
  }
}
