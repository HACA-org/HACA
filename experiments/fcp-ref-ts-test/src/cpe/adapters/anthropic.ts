import type { CPEAdapter, CPERequest, CPEResponse, ToolUseCall } from '../types.js'
import { requireEnv } from '../env.js'

const ANTHROPIC_API = 'https://api.anthropic.com/v1/messages'
const DEFAULT_MODEL = 'claude-sonnet-4-6'
const DEFAULT_MAX_TOKENS = 8192

interface AnthropicContent {
  type: string
  text?: string
  id?: string
  name?: string
  input?: Record<string, unknown>
}

interface AnthropicResponse {
  content: AnthropicContent[]
  stop_reason: string
  usage: { input_tokens: number; output_tokens: number }
}

export function createAnthropicAdapter(model = DEFAULT_MODEL): CPEAdapter {
  return {
    provider: 'anthropic',

    async invoke(request: CPERequest): Promise<CPEResponse> {
      const apiKey = requireEnv('ANTHROPIC_API_KEY')

      const body: Record<string, unknown> = {
        model,
        max_tokens: request.maxTokens ?? DEFAULT_MAX_TOKENS,
        system: request.system,
        messages: request.messages.map(m => ({
          role: m.role,
          content: m.content,
        })),
      }

      if (request.topology !== 'opaque' && request.tools?.length) {
        body['tools'] = request.tools
      }

      const res = await fetch(ANTHROPIC_API, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-api-key': apiKey,
          'anthropic-version': '2023-06-01',
        },
        body: JSON.stringify(body),
      })

      if (!res.ok) {
        throw new Error(`Anthropic error: ${res.status} ${await res.text()}`)
      }

      const data = await res.json() as AnthropicResponse

      const textBlocks = data.content.filter(b => b.type === 'text')
      const toolBlocks = data.content.filter(b => b.type === 'tool_use')

      const toolCalls: ToolUseCall[] = toolBlocks.map(b => ({
        id: b.id!,
        name: b.name!,
        input: b.input ?? {},
      }))

      return {
        content: textBlocks.map(b => b.text).join('') || null,
        toolCalls,
        usage: {
          inputTokens: data.usage.input_tokens,
          outputTokens: data.usage.output_tokens,
        },
        stopReason: data.stop_reason === 'tool_use' ? 'tool_use'
          : data.stop_reason === 'max_tokens' ? 'max_tokens'
          : 'end_turn',
      }
    },
  }
}
