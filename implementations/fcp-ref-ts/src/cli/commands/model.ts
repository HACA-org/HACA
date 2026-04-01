// fcp model — change the CPE backend for an entity without resetting it.
// Reads baseline.json, runs the same backend/API-key picker as fcp init,
// writes the new backend back to baseline.json.
import * as path from 'node:path'
import * as fs from 'node:fs/promises'
import { existsSync } from 'node:fs'
import { spawnSync } from 'node:child_process'
import { createInterface } from 'node:readline'
import type { Command } from 'commander'
import chalk from 'chalk'
import { readJson, writeJson, ensureDir, atomicWrite, fileExists } from '../../store/io.js'
import { createLayout } from '../../types/store.js'
import { refreshIntegrityDoc } from '../../sil/sil.js'
import { CLIError } from '../../types/cli.js'
import { prompt, select, hr, info, warn } from '../ui/prompt.js'
import { FCP_HOME, resolveEntityRoot } from '../entity.js'

const FCP_ENV_FILE = path.join(FCP_HOME, '.env')

// ─── Model catalog (mirrors init.ts) ─────────────────────────────────────────

const ANTHROPIC_MODELS = [
  'claude-opus-4-6',
  'claude-sonnet-4-6',
  'claude-haiku-4-5-20251001',
  'claude-opus-4-5-20251101',
  'claude-sonnet-4-20250514',
]

const OPENAI_MODELS = [
  'gpt-4o',
  'gpt-4o-mini',
  'o1',
  'o1-mini',
  'o3-mini',
]

const GOOGLE_MODELS = [
  'gemini-2.5-flash',
  'gemini-3-flash-preview',
  'gemini-3.1-flash-lite-preview',
  'gemini-3.1-pro-preview',
]

function listOllamaModels(): string[] {
  try {
    const result = spawnSync('curl', ['-s', 'http://localhost:11434/api/tags'], {
      encoding: 'utf8', timeout: 2000,
    })
    if (result.status !== 0 || !result.stdout) return []
    const data = JSON.parse(result.stdout) as { models?: Array<{ name: string }> }
    return (data.models ?? []).map(m => m.name)
  } catch {
    return []
  }
}

// ─── Readline setup ───────────────────────────────────────────────────────────

function makeRl() {
  return createInterface({ input: process.stdin, output: process.stdout })
}

// ─── API key management ───────────────────────────────────────────────────────

const API_KEY_VARS: Record<string, string> = {
  anthropic: 'ANTHROPIC_API_KEY',
  openai:    'OPENAI_API_KEY',
  google:    'GOOGLE_API_KEY',
}

async function readEnvFile(): Promise<Map<string, string>> {
  const map = new Map<string, string>()
  if (!await fileExists(FCP_ENV_FILE)) return map
  const raw = await fs.readFile(FCP_ENV_FILE, 'utf8')
  for (const line of raw.split('\n')) {
    const trimmed = line.trim()
    if (!trimmed || trimmed.startsWith('#')) continue
    const eq = trimmed.indexOf('=')
    if (eq < 1) continue
    map.set(trimmed.slice(0, eq).trim(), trimmed.slice(eq + 1).trim())
  }
  return map
}

async function writeEnvFile(entries: Map<string, string>): Promise<void> {
  await ensureDir(FCP_HOME)
  const lines = Array.from(entries.entries()).map(([k, v]) => `${k}=${v}`)
  await atomicWrite(FCP_ENV_FILE, lines.join('\n') + '\n')
}

async function promptApiKey(rl: ReturnType<typeof makeRl>, provider: string): Promise<void> {
  const envVar = API_KEY_VARS[provider]
  if (!envVar) return

  if (process.env[envVar]) {
    info(`${envVar} already set in environment`)
    return
  }

  const existing = await readEnvFile()
  if (existing.has(envVar)) {
    const masked = '*'.repeat(8) + (existing.get(envVar) ?? '').slice(-4)
    info(`${envVar} already saved (${masked})`)
    return
  }

  process.stdout.write(`\n  ${provider} requires an API key (stored in ~/.fcp/.env).\n\n`)
  const key = await prompt(rl, `  ${envVar}`, { hint: 'sk-...' })
  if (key) {
    existing.set(envVar, key)
    await writeEnvFile(existing)
    info(`Saved to ~/.fcp/.env`)
  } else {
    warn(`Skipped. Set ${envVar} in your shell or ~/.fcp/.env before running`)
  }
}

// ─── Backend picker ───────────────────────────────────────────────────────────

async function pickBackend(rl: ReturnType<typeof makeRl>): Promise<string> {
  const providers = [
    { label: 'Anthropic', description: 'Claude models' },
    { label: 'OpenAI', description: 'GPT-4, o1 models' },
    { label: 'Google', description: 'Gemini models' },
    { label: 'Ollama', description: 'Local models' },
  ]

  const providerRes = await select(rl, 'CPE Backend — Select provider:', providers)
  const providerIdx = providerRes.index
  let models: string[]
  let providerPrefix: string

  if (providerIdx === 1) {
    models = OPENAI_MODELS
    providerPrefix = 'openai'
  } else if (providerIdx === 2) {
    models = GOOGLE_MODELS
    providerPrefix = 'google'
  } else if (providerIdx === 3) {
    providerPrefix = 'ollama'
    process.stdout.write(`\n${chalk.dim('  Detecting local Ollama models...')}\n`)
    models = listOllamaModels()
    if (models.length === 0) {
      warn('No Ollama models found (is Ollama running?)')
      process.stdout.write(`\n`)
      const manual = await prompt(rl, '  Model name', { default: 'llama3.2', hint: 'e.g., mistral, neural-chat' })
      return `ollama:${manual}`
    }
  } else {
    models = ANTHROPIC_MODELS
    providerPrefix = 'anthropic'
  }

  const modelOptions = models.map(m => ({ label: m }))
  const modelRes = await select(rl, 'Select model:', modelOptions, 0)
  const model = models[modelRes.index]!

  return `${providerPrefix}:${model}`
}

// ─── Main ─────────────────────────────────────────────────────────────────────

async function runModel(opts: { entity?: string }): Promise<void> {
  if (!process.stdin.isTTY) {
    throw new CLIError('fcp model requires an interactive terminal', 1)
  }

  const entityRoot = await resolveEntityRoot(opts.entity)
  const baselinePath = path.join(entityRoot, 'state', 'baseline.json')

  if (!existsSync(baselinePath)) {
    throw new CLIError('baseline.json not found. Run `fcp init`.', 1)
  }

  const baseline = await readJson(baselinePath) as Record<string, unknown>
  const cpe = baseline['cpe'] as Record<string, unknown> | undefined
  const currentBackend = typeof cpe?.['backend'] === 'string' ? cpe['backend'] : 'unknown'

  process.stdout.write('\n')
  hr()
  process.stdout.write('  FCP — Change CPE Backend\n')
  hr()
  process.stdout.write(`  Current: ${currentBackend}\n`)

  const rl = makeRl()
  try {
    const backend = await pickBackend(rl)
    const provider = backend.split(':')[0]!
    await promptApiKey(rl, provider)

    // Patch baseline.json in-place
    const updated = { ...baseline, cpe: { ...(cpe ?? {}), backend } }
    await writeJson(baselinePath, updated)

    // Refresh integrity.json so the next boot doesn't detect drift on baseline.json.
    // Only needed after FAP (imprint exists); pre-activation integrity.json is rebuilt by FAP anyway.
    const layout = createLayout(entityRoot)
    if (await fileExists(layout.memory.imprint) && await fileExists(layout.state.integrity)) {
      await refreshIntegrityDoc(layout)
      process.stdout.write('\n')
      hr()
      process.stdout.write(`  Backend updated: ${currentBackend} → ${backend}\n`)
      process.stdout.write(`  integrity.json refreshed.\n`)
    } else {
      process.stdout.write('\n')
      hr()
      process.stdout.write(`  Backend updated: ${currentBackend} → ${backend}\n`)
    }
    hr()
    process.stdout.write('\n')
  } finally {
    rl.close()
  }
}

export function registerModel(program: Command): void {
  program
    .command('model')
    .description('Change the CPE model (uses default entity)')
    .action(async function (this: Command) {
      const entity = (this.optsWithGlobals() as { entity?: string }).entity
      await runModel(entity ? { entity } : {})
    })
}
