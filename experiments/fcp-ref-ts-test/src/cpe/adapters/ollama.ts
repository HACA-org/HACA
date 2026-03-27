import type { CPEAdapter, CPERequest, CPEResponse, ModelInfo } from '../types.js'

const OLLAMA_BASE = 'http://localhost:11434'

interface OllamaModel {
  name: string
  details?: { parameter_size?: string }
}

interface OllamaMessage {
  role: string
  content: string
}

interface OllamaResponse {
  message: { content: string }
  done: boolean
  prompt_eval_count?: number
  eval_count?: number
}

export async function detectOllama(): Promise<boolean> {
  try {
    const res = await fetch(`${OLLAMA_BASE}/api/tags`, { signal: AbortSignal.timeout(2000) })
    return res.ok
  } catch {
    return false
  }
}

export async function listOllamaModels(): Promise<ModelInfo[]> {
  try {
    const res = await fetch(`${OLLAMA_BASE}/api/tags`, { signal: AbortSignal.timeout(3000) })
    if (!res.ok) return []
    const data = await res.json() as { models: OllamaModel[] }
    return (data.models ?? []).map(m => ({
      id: m.name,
      provider: 'ollama',
      contextWindow: 8192, // default; Ollama doesn't expose this via API
    }))
  } catch {
    return []
  }
}

export function createOllamaAdapter(model: string): CPEAdapter {
  return {
    provider: 'ollama',

    async invoke(request: CPERequest): Promise<CPEResponse> {
      const messages: OllamaMessage[] = [
        { role: 'system', content: request.system },
        ...request.messages.map(m => ({
          role: m.role,
          content: typeof m.content === 'string' ? m.content : JSON.stringify(m.content),
        })),
      ]

      const res = await fetch(`${OLLAMA_BASE}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model, messages, stream: false }),
      })

      if (!res.ok) {
        throw new Error(`Ollama error: ${res.status} ${await res.text()}`)
      }

      const data = await res.json() as OllamaResponse

      return {
        content: data.message.content,
        toolCalls: [],
        usage: {
          inputTokens: data.prompt_eval_count ?? 0,
          outputTokens: data.eval_count ?? 0,
        },
        stopReason: 'end_turn',
      }
    },
  }
}
