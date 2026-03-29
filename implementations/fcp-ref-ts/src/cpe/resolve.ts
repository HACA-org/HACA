import * as fs   from 'node:fs'
import * as path from 'node:path'
import * as os   from 'node:os'
import type { CPEAdapter } from '../types/cpe.js'
import { CPEConfigError }  from '../types/cpe.js'
import { createAnthropicAdapter } from './anthropic.js'
import { createOpenAIAdapter }    from './openai.js'
import { createGoogleAdapter }    from './google.js'
import { createOllamaAdapter }    from './ollama.js'

// Load ~/.fcp/.env into process.env (dotenv-style, no deps).
// Only sets keys that are not already set — shell env takes precedence.
function loadFcpEnv(): void {
  const envFile = path.join(os.homedir(), '.fcp', '.env')
  let raw: string
  try { raw = fs.readFileSync(envFile, 'utf8') } catch { return }
  for (const line of raw.split('\n')) {
    const trimmed = line.trim()
    if (!trimmed || trimmed.startsWith('#')) continue
    const eq = trimmed.indexOf('=')
    if (eq < 1) continue
    const key = trimmed.slice(0, eq).trim()
    const val = trimmed.slice(eq + 1).trim().replace(/^["']|["']$/g, '')
    if (key && !(key in process.env)) process.env[key] = val
  }
}

// Parse "<provider>:<model>" — model may itself contain colons (e.g., "ollama:llama3.2:latest")
function parseBackend(backend: string): { provider: string; model: string } {
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
    throw new CPEConfigError(`${provider}: ${name} is not set — add it to ~/.fcp/.env or export it in your shell`)
  }
  return val
}

export function resolveAdapter(backend: string): CPEAdapter {
  loadFcpEnv()
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
