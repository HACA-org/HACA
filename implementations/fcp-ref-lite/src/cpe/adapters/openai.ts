import type { CPEAdapter, CPERequest, CPEResponse, ToolUseCall } from '../types.js'
import { requireEnv } from '../env.js'

const OPENAI_API = 'https://api.openai.com/v1/chat/completions'
const DEFAULT_MODEL = 'gpt-4o'
const DEFAULT_MAX_TOKENS = 8192

interface OpenAIMessage { role: string; content: string }
interface OpenAIToolCall {
  id: string
  function: { name: string; arguments: string }
}
interface OpenAIChoice {
  message: { content: string | null; tool_calls?: OpenAIToolCall[] }
  finish_reason: string
}
interface OpenAIResponse {
  choices: OpenAIChoice[]
  usage: { prompt_tokens: number; completion_tokens: number }
}

export function createOpenAIAdapter(model = DEFAULT_MODEL): CPEAdapter {
  return {
    provider: 'openai',

    async invoke(request: CPERequest): Promise<CPEResponse> {
      const apiKey = requireEnv('OPENAI_API_KEY')

      const messages: OpenAIMessage[] = [
        { role: 'system', content: request.system },
        ...request.messages.map(m => ({
          role: m.role,
          content: typeof m.content === 'string' ? m.content : JSON.stringify(m.content),
        })),
      ]

      const body: Record<string, unknown> = {
        model,
        max_tokens: request.maxTokens ?? DEFAULT_MAX_TOKENS,
        messages,
      }

      if (request.topology !== 'opaque' && request.tools?.length) {
        body['tools'] = request.tools.map(t => ({
          type: 'function',
          function: { name: t.name, description: t.description, parameters: t.input_schema },
        }))
      }

      const res = await fetch(OPENAI_API, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${apiKey}`,
        },
        body: JSON.stringify(body),
      })

      if (!res.ok) {
        throw new Error(`OpenAI error: ${res.status} ${await res.text()}`)
      }

      const data = await res.json() as OpenAIResponse
      const choice = data.choices[0]!

      const toolCalls: ToolUseCall[] = (choice.message.tool_calls ?? []).map(tc => ({
        id: tc.id,
        name: tc.function.name,
        input: JSON.parse(tc.function.arguments) as Record<string, unknown>,
      }))

      return {
        content: choice.message.content,
        toolCalls,
        usage: {
          inputTokens: data.usage.prompt_tokens,
          outputTokens: data.usage.completion_tokens,
        },
        stopReason: choice.finish_reason === 'tool_calls' ? 'tool_use'
          : choice.finish_reason === 'length' ? 'max_tokens'
          : 'end_turn',
      }
    },
  }
}
