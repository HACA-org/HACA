import type { CPEAdapter, CPERequest, CPEResponse } from '../types/cpe.js'
import { CPEInvokeError } from '../types/cpe.js'
import { normalizeAnthropic } from './normalize.js'

const CONTEXT: Record<string, number> = {
  'claude-opus-4-6':           200000,
  'claude-sonnet-4-6':         200000,
  'claude-haiku-4-5':          200000,
  'claude-haiku-4-5-20251001': 200000,
}

const API_URL = 'https://api.anthropic.com/v1/messages'

// Anthropic's content format matches our internal CPERequest format exactly.
// No message transformation needed — pass through directly.
function toBody(model: string, req: CPERequest): unknown {
  return {
    model,
    max_tokens: 8192,
    ...(req.system !== undefined ? { system: req.system } : {}),
    messages: req.messages,
    tools: req.tools.map(t => ({
      name:         t.name,
      description:  t.description,
      input_schema: t.input_schema,
    })),
  }
}

export function createAnthropicAdapter(model: string, apiKey: string): CPEAdapter {
  return {
    provider:      'anthropic',
    model,
    contextWindow: CONTEXT[model] ?? 200000,

    async invoke(req: CPERequest): Promise<CPEResponse> {
      const resp = await fetch(API_URL, {
        method: 'POST',
        headers: {
          'content-type':      'application/json',
          'x-api-key':         apiKey,
          'anthropic-version': '2023-06-01',
        },
        body: JSON.stringify(toBody(model, req)),
      })
      if (!resp.ok) {
        throw new CPEInvokeError(
          `Anthropic API error ${resp.status}: ${resp.statusText}`,
          resp.status,
        )
      }
      return normalizeAnthropic(await resp.json() as unknown)
    },
  }
}
