import type { CPEAdapter, CPERequest, CPEResponse } from '../types.js'
import { requireEnv } from '../env.js'

const DEFAULT_MODEL = 'gemini-2.0-flash'
const DEFAULT_MAX_TOKENS = 8192

interface GeminiPart { text: string }
interface GeminiContent { role: string; parts: GeminiPart[] }
interface GeminiCandidate {
  content: GeminiContent
  finishReason: string
}
interface GeminiResponse {
  candidates: GeminiCandidate[]
  usageMetadata?: { promptTokenCount: number; candidatesTokenCount: number }
}

export function createGoogleAdapter(model = DEFAULT_MODEL): CPEAdapter {
  return {
    provider: 'google',

    async invoke(request: CPERequest): Promise<CPEResponse> {
      const apiKey = requireEnv('GOOGLE_API_KEY')
      const url = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${apiKey}`

      const contents: GeminiContent[] = request.messages.map(m => ({
        role: m.role === 'assistant' ? 'model' : 'user',
        parts: [{ text: typeof m.content === 'string' ? m.content : JSON.stringify(m.content) }],
      }))

      const body: Record<string, unknown> = {
        system_instruction: { parts: [{ text: request.system }] },
        contents,
        generationConfig: { maxOutputTokens: request.maxTokens ?? DEFAULT_MAX_TOKENS },
      }

      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })

      if (!res.ok) {
        throw new Error(`Google error: ${res.status} ${await res.text()}`)
      }

      const data = await res.json() as GeminiResponse
      const candidate = data.candidates[0]
      const text = candidate?.content.parts.map(p => p.text).join('') ?? ''

      return {
        content: text || null,
        toolCalls: [],
        usage: {
          inputTokens: data.usageMetadata?.promptTokenCount ?? 0,
          outputTokens: data.usageMetadata?.candidatesTokenCount ?? 0,
        },
        stopReason: candidate?.finishReason === 'MAX_TOKENS' ? 'max_tokens' : 'end_turn',
      }
    },
  }
}
