// fcp model — change the CPE backend for an entity without resetting it.
// Reads baseline.json, runs the same backend/API-key picker as fcp init,
// writes the new backend back to baseline.json.
import * as path from 'node:path'
import * as os from 'node:os'
import * as fs from 'node:fs/promises'
import { existsSync } from 'node:fs'
import { spawnSync } from 'node:child_process'
import { createInterface } from 'node:readline'
import type { Command } from 'commander'
import { readJson, writeJson, ensureDir, atomicWrite, fileExists } from '../../store/io.js'
import { createLayout } from '../../types/store.js'
import { refreshIntegrityDoc } from '../../sil/sil.js'
import { CLIError } from '../../types/cli.js'

const FCP_HOME     = path.join(os.homedir(), '.fcp')
const ENTITIES_DIR = path.join(FCP_HOME, 'entities')
const DEFAULT_FILE = path.join(FCP_HOME, 'default')
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

// ─── Readline helpers ─────────────────────────────────────────────────────────

function makeRl() {
  return createInterface({ input: process.stdin, output: process.stdout })
}

function ask(rl: ReturnType<typeof makeRl>, question: string, def = ''): Promise<string> {
  return new Promise(resolve => {
    rl.question(def ? `${question} [${def}]: ` : `${question}: `, a => {
      resolve(a.trim() || def)
    })
  })
}

function hr(label = '') {
  if (label) {
    process.stdout.write(`\n  ── ${label} ${'─'.repeat(Math.max(0, 54 - label.length))}\n`)
  } else {
    process.stdout.write(`  ${'─'.repeat(60)}\n`)
  }
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
    process.stdout.write(`  ${envVar} already set in environment — skipping.\n`)
    return
  }

  const existing = await readEnvFile()
  if (existing.has(envVar)) {
    const masked = '*'.repeat(8) + (existing.get(envVar) ?? '').slice(-4)
    process.stdout.write(`  ${envVar} already saved (${masked}) — skipping.\n`)
    return
  }

  process.stdout.write(`\n  ${provider} requires an API key (stored in ~/.fcp/.env).\n`)
  const key = await ask(rl, `  ${envVar}`)
  if (key) {
    existing.set(envVar, key)
    await writeEnvFile(existing)
    process.stdout.write(`  → Saved to ~/.fcp/.env\n`)
  } else {
    process.stdout.write(`  Skipped. Set ${envVar} in your shell or ~/.fcp/.env before running.\n`)
  }
}

// ─── Backend picker ───────────────────────────────────────────────────────────

async function pickBackend(rl: ReturnType<typeof makeRl>): Promise<string> {
  hr('CPE Backend')
  process.stdout.write('\n  Provider:\n')
  process.stdout.write('    1. Anthropic\n')
  process.stdout.write('    2. OpenAI\n')
  process.stdout.write('    3. Google\n')
  process.stdout.write('    4. Ollama (local)\n\n')

  const providerRaw = await ask(rl, '  Provider', '1')

  let models: string[]
  let providerPrefix: string

  if (providerRaw === '2') {
    models = OPENAI_MODELS
    providerPrefix = 'openai'
  } else if (providerRaw === '3') {
    models = GOOGLE_MODELS
    providerPrefix = 'google'
  } else if (providerRaw === '4') {
    providerPrefix = 'ollama'
    process.stdout.write('\n  Detecting local Ollama models...\n')
    models = listOllamaModels()
    if (models.length === 0) {
      process.stdout.write('  No Ollama models found (is Ollama running?).\n')
      process.stdout.write('  Enter model name manually.\n\n')
      const manual = await ask(rl, '  Model', 'llama3.2')
      return `ollama:${manual}`
    }
  } else {
    models = ANTHROPIC_MODELS
    providerPrefix = 'anthropic'
  }

  process.stdout.write('\n  Available models:\n')
  models.forEach((m, i) => process.stdout.write(`    ${i + 1}. ${m}\n`))
  process.stdout.write('\n')

  const modelRaw = await ask(rl, '  Model number or name', '1')
  const idx = parseInt(modelRaw, 10) - 1
  const model = (idx >= 0 && idx < models.length) ? models[idx]! : modelRaw

  return `${providerPrefix}:${model}`
}

// ─── Entity resolution ────────────────────────────────────────────────────────

async function resolveEntityRoot(entityId?: string): Promise<string> {
  if (entityId) {
    const root = path.join(ENTITIES_DIR, entityId)
    if (!existsSync(root)) throw new CLIError(`Entity not found: ${entityId}`, 1)
    return root
  }

  if (existsSync(DEFAULT_FILE)) {
    const id = (await fs.readFile(DEFAULT_FILE, 'utf8')).trim()
    if (id) {
      const root = path.join(ENTITIES_DIR, id)
      if (existsSync(root)) return root
    }
  }

  if (existsSync(ENTITIES_DIR)) {
    const entries = await fs.readdir(ENTITIES_DIR, { withFileTypes: true })
    const dirs = entries.filter(e => e.isDirectory())
    if (dirs.length === 1) return path.join(ENTITIES_DIR, dirs[0]!.name)
  }

  throw new CLIError('No entity found. Run `fcp init` to create one.', 1)
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
