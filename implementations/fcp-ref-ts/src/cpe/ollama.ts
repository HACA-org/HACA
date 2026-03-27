import type { CPEAdapter, CPERequest, CPEResponse, TextBlock } from '../types/cpe.js'
import { CPEInvokeError } from '../types/cpe.js'
import { normalizeOllama } from './normalize.js'

const DEFAULT_BASE = 'http://localhost:11434'

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
          ...req.messages.map(m => ({
            role:    m.role,
            // Ollama text-only: collapse content blocks to plain text
            content: typeof m.content === 'string'
              ? m.content
              : m.content
                  .filter((b): b is TextBlock => b.type === 'text')
                  .map(b => b.text)
                  .join(''),
          })),
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
