// fcp init — interactive entity scaffolding.
// Separates interactive flow (readline prompts) from file generation (templates/).
// Operator enrollment (name/email) is collected by FAP on first boot — not here.
import * as path from 'node:path'
import * as os from 'node:os'
import * as fs from 'node:fs/promises'
import { existsSync } from 'node:fs'
import { spawnSync } from 'node:child_process'
import { createInterface } from 'node:readline'
import type { Command } from 'commander'
import { writeJson, ensureDir, atomicWrite, fileExists } from '../../store/io.js'
import { makeBaselineJson } from '../templates/baseline.js'
import {
  makeIntegrityDoc, personaIdentity, personaValues,
  personaConstraints, personaProtocol, bootMd, GITIGNORE,
  type Profile,
} from '../templates/integrity.js'
import { CLIError } from '../../types/cli.js'
import type { AuthorizationScope } from '../../types/formats/baseline.js'

const FCP_HOME     = path.join(os.homedir(), '.fcp')
const ENTITIES_DIR = path.join(FCP_HOME, 'entities')
const DEFAULT_FILE = path.join(FCP_HOME, 'default')

// ─── Model catalog ────────────────────────────────────────────────────────────

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

function confirm(rl: ReturnType<typeof makeRl>, question: string, defYes = true): Promise<boolean> {
  return new Promise(resolve => {
    const hint = defYes ? 'Y/n' : 'y/N'
    rl.question(`${question} [${hint}]: `, a => {
      const s = a.trim().toLowerCase()
      resolve(s === '' ? defYes : s === 'y' || s === 'yes')
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

// ─── Entity registry ──────────────────────────────────────────────────────────

async function listEntities(): Promise<string[]> {
  if (!existsSync(ENTITIES_DIR)) return []
  const entries = await fs.readdir(ENTITIES_DIR, { withFileTypes: true })
  return entries.filter(e => e.isDirectory()).map(e => e.name)
}

async function getDefault(): Promise<string | null> {
  if (!existsSync(DEFAULT_FILE)) return null
  return (await fs.readFile(DEFAULT_FILE, 'utf8')).trim() || null
}

async function setDefault(id: string): Promise<void> {
  await ensureDir(FCP_HOME)
  await atomicWrite(DEFAULT_FILE, id + '\n')
}

// ─── Scaffold helpers ─────────────────────────────────────────────────────────

async function scaffoldEntity(root: string, profile: Profile): Promise<void> {
  const dirs = [
    path.join(root, 'memory', 'episodic'),
    path.join(root, 'memory', 'semantic'),
    path.join(root, 'memory', 'active-context'),
    path.join(root, 'state', 'sentinels'),
    path.join(root, 'state', 'operator-notifications'),
    path.join(root, 'io', 'inbox', 'presession'),
    path.join(root, 'io', 'spool'),
    path.join(root, 'persona'),
    path.join(root, 'skills'),
    path.join(root, 'hooks'),
  ]
  for (const d of dirs) await ensureDir(d)

  // Persona files
  await atomicWrite(path.join(root, 'persona', 'identity.md'),    personaIdentity(profile))
  await atomicWrite(path.join(root, 'persona', 'values.md'),      personaValues())
  await atomicWrite(path.join(root, 'persona', 'constraints.md'), personaConstraints(profile))
  await atomicWrite(path.join(root, 'persona', 'protocol.md'),    personaProtocol())

  // boot.md
  await atomicWrite(path.join(root, 'boot.md'), bootMd())

  // Empty session log + working memory
  await atomicWrite(path.join(root, 'memory', 'session.jsonl'), '')
  await writeJson(path.join(root, 'memory', 'working-memory.json'), { version: '1.0', entries: [] })

  // Integrity document (empty hashes — FAP will populate)
  await writeJson(path.join(root, 'state', 'integrity.json'), makeIntegrityDoc())

  // Skills index
  await writeJson(path.join(root, 'skills', 'index.json'), { version: '1.0', skills: [], aliases: {} })

  // .gitignore
  await atomicWrite(path.join(root, '.gitignore'), GITIGNORE)
}

async function gitInitAndCommit(root: string, entityId: string): Promise<void> {
  const run = (args: string[]) => spawnSync('git', args, { cwd: root, encoding: 'utf8' })

  // Skip if already a git repo
  if (!existsSync(path.join(root, '.git'))) {
    const init = run(['init'])
    if (init.status !== 0) {
      process.stdout.write(`  ⚠  git init failed: ${init.stderr.trim()}\n`)
      return
    }
  }

  run(['add', '.'])
  const commit = run(['commit', '-m', `init: scaffold entity ${entityId}`])
  if (commit.status !== 0) {
    process.stdout.write(`  ⚠  git commit failed: ${commit.stderr.trim()}\n`)
  }
}

// ─── API key management ───────────────────────────────────────────────────────

const FCP_ENV_FILE = path.join(FCP_HOME, '.env')

const API_KEY_VARS: Record<string, string> = {
  anthropic: 'ANTHROPIC_API_KEY',
  openai:    'OPENAI_API_KEY',
  google:    'GOOGLE_API_KEY',
}

// Read current ~/.fcp/.env as a key→value map (unparsed lines preserved).
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

// Prompt for API key for the chosen provider (skip if already set in env or .env file).
async function promptApiKey(rl: ReturnType<typeof makeRl>, provider: string): Promise<void> {
  const envVar = API_KEY_VARS[provider]
  if (!envVar) return  // ollama — no key needed

  // Already set in shell env — skip
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

// ─── Model picker ─────────────────────────────────────────────────────────────

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

// ─── Authorization scope picker (HACA-Evolve only) ───────────────────────────

async function pickAuthScope(rl: ReturnType<typeof makeRl>): Promise<AuthorizationScope> {
  hr('Authorization Scope')
  process.stdout.write('\n  Define what the entity may do autonomously without Operator approval.\n\n')

  const autonomousEvolution = await confirm(rl, '  Autonomous file evolution (fileWrite, fileDelete, jsonMerge)', false)
  const autonomousSkills    = await confirm(rl, '  Autonomous skill installation (skillInstall)', false)
  const operatorMemory      = await confirm(rl, '  Autonomous memory promotion (promoteSlugs)', false)

  const renewalRaw = await ask(rl, '  Scope renewal period in days (0 = no expiry)', '0')
  const renewalDays = Math.max(0, parseInt(renewalRaw, 10) || 0)

  return {
    autonomousEvolution,
    autonomousSkills,
    operatorMemory,
    renewalDays,
    grantedAt: new Date().toISOString(),
  }
}

// ─── Main flow ────────────────────────────────────────────────────────────────

async function runInit(): Promise<void> {
  if (!process.stdin.isTTY) {
    throw new CLIError('fcp init requires an interactive terminal', 1)
  }

  const rl = makeRl()
  try {
    process.stdout.write('\n')
    hr()
    process.stdout.write('  FCP — Filesystem Cognitive Platform\n')
    process.stdout.write('  HACA v1.0 Reference Implementation\n')
    hr()
    process.stdout.write('  ⚠  Experimental software. Review security before production use.\n')
    hr()
    process.stdout.write('\n')

    // ── Entity ID ────────────────────────────────────────────────────────────
    const existing   = await listEntities()
    const currentDef = await getDefault()
    if (existing.length > 0) {
      process.stdout.write('  Existing entities:\n')
      for (const eid of existing) {
        process.stdout.write(`    ${eid}${eid === currentDef ? '  (default)' : ''}\n`)
      }
      process.stdout.write('\n')
    }

    const rawId    = await ask(rl, '  Entity ID', 'my-entity')
    const entityId = rawId.toLowerCase().replace(/\s+/g, '-')
    if (!entityId || entityId.includes('/') || entityId.includes('..')) {
      throw new CLIError('Invalid entity ID', 1)
    }

    const entityRoot = path.join(ENTITIES_DIR, entityId)
    const isExisting = existsSync(entityRoot)

    if (isExisting) {
      process.stdout.write(`\n  Existing entity at ${entityRoot}.\n`)
      const reset = await confirm(rl, '  Factory reset (wipe and re-init)?', false)
      if (!reset) { process.stdout.write('  Cancelled.\n'); return }

      // Wipe content but preserve .git
      const items = await fs.readdir(entityRoot, { withFileTypes: true })
      for (const item of items) {
        if (item.name === '.git') continue
        await fs.rm(path.join(entityRoot, item.name), { recursive: true, force: true })
      }
    }

    // ── Profile ──────────────────────────────────────────────────────────────
    hr('Profile')
    process.stdout.write('\n  1. HACA-Core   — Zero-autonomy (transparent topology)\n')
    process.stdout.write(  '  2. HACA-Evolve — Supervised autonomy (opaque topology)\n\n')
    const profileRaw = await ask(rl, '  Choice', '1')
    const profile: Profile = profileRaw === '2' ? 'haca-evolve' : 'haca-core'
    const topology          = profile === 'haca-evolve' ? 'opaque' : 'transparent'

    // ── Authorization scope (HACA-Evolve only) ────────────────────────────────
    let authorizationScope: AuthorizationScope | undefined
    if (profile === 'haca-evolve') {
      authorizationScope = await pickAuthScope(rl)
    }

    // ── CPE Backend ───────────────────────────────────────────────────────────
    const backend = await pickBackend(rl)
    const backendProvider = backend.split(':')[0]!
    await promptApiKey(rl, backendProvider)

    // ── Scaffold ─────────────────────────────────────────────────────────────
    hr('Creating entity')
    process.stdout.write('\n')

    await scaffoldEntity(entityRoot, profile)
    await writeJson(path.join(entityRoot, 'state', 'baseline.json'), makeBaselineJson({
      entityId, topology, backend, fallbackTokens: 200_000,
      ...(authorizationScope ? { authorizationScope } : {}),
    }))

    // git init + first commit
    await gitInitAndCommit(entityRoot, entityId)

    // Set default if none
    if (!currentDef) await setDefault(entityId)

    // ── Summary ──────────────────────────────────────────────────────────────
    process.stdout.write('  Entity scaffold created.\n')
    hr()
    process.stdout.write(`  entity:   ${entityId}\n`)
    process.stdout.write(`  path:     ${entityRoot}\n`)
    process.stdout.write(`  profile:  ${profile}\n`)
    process.stdout.write(`  backend:  ${backend}\n`)
    if (authorizationScope) {
      process.stdout.write(`  scope:    evolution=${authorizationScope.autonomousEvolution} skills=${authorizationScope.autonomousSkills} memory=${authorizationScope.operatorMemory} renewal=${authorizationScope.renewalDays}d\n`)
    }
    hr()
    process.stdout.write('\n  First boot will run FAP (First Activation Protocol).\n')
    process.stdout.write('  Run:  fcp\n\n')

  } finally {
    rl.close()
  }
}

export function registerInit(program: Command): void {
  program
    .command('init')
    .description('Install or reset an FCP entity')
    .action(async () => {
      await runInit()
    })
}
