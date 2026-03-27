import type { CPEAdapter, CPERequest, CPEResponse, Profile, ModelInfo } from './types.js'
import { createOllamaAdapter, detectOllama, listOllamaModels } from './adapters/ollama.js'
import { createAnthropicAdapter } from './adapters/anthropic.js'
import { createGoogleAdapter } from './adapters/google.js'
import { createOpenAIAdapter } from './adapters/openai.js'
import { loadEnv, getEnv } from './env.js'

export interface CPEConfig {
  provider: string
  model: string
  profile: Profile
}

export function createCPE(config: CPEConfig) {
  const adapter = resolveAdapter(config)

  async function invoke(request: CPERequest): Promise<CPEResponse> {
    // haca-core: strip tools in opaque topology (pairing not available)
    if (config.profile === 'haca-core') {
      request = { ...request, topology: 'transparent' }
    }

    return adapter.invoke(request)
  }

  return { invoke, provider: adapter.provider }
}

export function resolveAdapter(config: CPEConfig): CPEAdapter {
  switch (config.provider) {
    case 'ollama':    return createOllamaAdapter(config.model)
    case 'anthropic': return createAnthropicAdapter(config.model)
    case 'google':    return createGoogleAdapter(config.model)
    case 'openai':    return createOpenAIAdapter(config.model)
    default: throw new Error(`Unknown CPE provider: ${config.provider}`)
  }
}

export function createPairingAdapter(config: CPEConfig, profile: Profile): CPEAdapter {
  if (profile === 'haca-core') {
    throw new Error('Pairing is not available for haca-core profile')
  }
  return resolveAdapter({ ...config, })
}

/** Auto-detect available providers in priority order: Ollama → env keys */
export async function detectAvailableModels(): Promise<ModelInfo[]> {
  await loadEnv()
  const models: ModelInfo[] = []

  // 1. Ollama — auto-detect local models
  if (await detectOllama()) {
    models.push(...await listOllamaModels())
  }

  // 2. Anthropic
  if (getEnv('ANTHROPIC_API_KEY')) {
    models.push(
      { id: 'claude-opus-4-6', provider: 'anthropic', contextWindow: 200000 },
      { id: 'claude-sonnet-4-6', provider: 'anthropic', contextWindow: 200000 },
      { id: 'claude-haiku-4-5-20251001', provider: 'anthropic', contextWindow: 200000 },
    )
  }

  // 3. Google
  if (getEnv('GOOGLE_API_KEY')) {
    models.push(
      { id: 'gemini-2.5-pro', provider: 'google', contextWindow: 1000000 },
      { id: 'gemini-2.0-flash', provider: 'google', contextWindow: 1000000 },
    )
  }

  // 4. OpenAI
  if (getEnv('OPENAI_API_KEY')) {
    models.push(
      { id: 'gpt-4o', provider: 'openai', contextWindow: 128000 },
      { id: 'gpt-4o-mini', provider: 'openai', contextWindow: 128000 },
    )
  }

  return models
}
