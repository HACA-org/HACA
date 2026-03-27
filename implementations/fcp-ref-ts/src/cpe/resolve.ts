import type { CPEAdapter } from '../types/cpe.js'
import { CPEConfigError }  from '../types/cpe.js'
import { createAnthropicAdapter } from './anthropic.js'
import { createOpenAIAdapter }    from './openai.js'
import { createGoogleAdapter }    from './google.js'
import { createOllamaAdapter }    from './ollama.js'

// Parse "<provider>:<model>" — model may itself contain colons (e.g., "ollama:llama3.2:latest")
function parseBackend(backend: string): { provider: string; model: string } {
  if (backend === 'auto') return { provider: 'anthropic', model: 'claude-opus-4-6' }
  const idx = backend.indexOf(':')
  if (idx < 1) {
    throw new CPEConfigError(
      `Invalid backend format: "${backend}" — expected "<provider>:<model>" (e.g. "anthropic:claude-opus-4-6")`,
    )
  }
  return { provider: backend.slice(0, idx), model: backend.slice(idx + 1) }
}

function requireEnv(name: string, provider: string): string {
  const val = process.env[name]
  if (val === undefined || val === '') {
    throw new CPEConfigError(`${provider}: ${name} environment variable is not set`)
  }
  return val
}

export function resolveAdapter(backend: string): CPEAdapter {
  const { provider, model } = parseBackend(backend)

  switch (provider) {
    case 'anthropic':
      return createAnthropicAdapter(model, requireEnv('ANTHROPIC_API_KEY', 'anthropic'))

    case 'openai':
      return createOpenAIAdapter(model, requireEnv('OPENAI_API_KEY', 'openai'))

    case 'google':
      return createGoogleAdapter(model, requireEnv('GOOGLE_API_KEY', 'google'))

    case 'ollama':
      return createOllamaAdapter(model, process.env['OLLAMA_BASE_URL'])

    default:
      throw new CPEConfigError(
        `Unknown provider: "${provider}" — supported: anthropic, openai, google, ollama`,
      )
  }
}
