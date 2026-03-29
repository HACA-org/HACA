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
import chalk from 'chalk'
import { writeJson, ensureDir, atomicWrite, fileExists } from '../../store/io.js'
import { makeBaselineJson } from '../templates/baseline.js'
import {
  makeIntegrityDoc, personaIdentity, personaValues,
  personaConstraints, personaProtocol, bootMd, GITIGNORE,
  type Profile,
} from '../templates/integrity.js'
import { CLIError } from '../../types/cli.js'
import type { AuthorizationScope } from '../../types/formats/baseline.js'
import { prompt, confirm, select, hr, info, warn, header } from '../ui/prompt.js'

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

// ─── Readline setup ───────────────────────────────────────────────────────────
// Use a single readline instance throughout init flow to avoid stdin state issues.
// selectInteractive uses raw mode; a shared readline prevents state corruption.

function makeRl() {
  return createInterface({ input: process.stdin, output: process.stdout, terminal: false })
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
    info(`${envVar} already set in environment`)
    return
  }

  const existing = await readEnvFile()
  if (existing.has(envVar)) {
    const masked = '*'.repeat(8) + (existing.get(envVar) ?? '').slice(-4)
    info(`${envVar} already saved (${masked})`)
    return
  }

  process.stdout.write(`\n  ${chalk.bold(provider)} requires an API key (stored in ${chalk.dim('~/.fcp/.env')}).\n\n`)
  const key = await prompt(rl, `  ${envVar}`, { hint: 'sk-...' })
  if (key) {
    existing.set(envVar, key)
    await writeEnvFile(existing)
    info(`Saved to ${chalk.dim('~/.fcp/.env')}`)
  } else {
    warn(`Skipped. Set ${envVar} in your shell or ~/.fcp/.env before running`)
  }
}

// ─── Model picker ─────────────────────────────────────────────────────────────

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

// ─── Authorization scope picker (HACA-Evolve only) ───────────────────────────

async function pickAuthScope(rl: ReturnType<typeof makeRl>): Promise<AuthorizationScope> {
  hr('Authorization Scope')
  process.stdout.write('\nDefine what the entity may do autonomously without Operator approval.\n\n')

  const autonomousEvolution = await confirm(
    rl,
    '  Allow file evolution (fileWrite, fileDelete, jsonMerge)',
    false,
  )
  const autonomousSkills = await confirm(
    rl,
    '  Allow skill installation (skillInstall)',
    false,
  )
  const operatorMemory = await confirm(
    rl,
    '  Allow memory promotion (promoteSlugs)',
    false,
  )

  process.stdout.write('\n')
  const renewalDays = parseInt(
    await prompt(rl, '  Renewal period (days)', { default: '0', hint: '0 = no expiry' }),
    10,
  ) || 0

  return {
    autonomousEvolution,
    autonomousSkills,
    operatorMemory,
    renewalDays: Math.max(0, renewalDays),
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
    header('FCP — Filesystem Cognitive Platform', 'HACA v1.0 Reference Implementation')
    warn('Experimental software. Review security before production use.')
    process.stdout.write('\n')

    // ── Entity ID ────────────────────────────────────────────────────────────
    const existing = await listEntities()
    const currentDef = await getDefault()
    if (existing.length > 0) {
      process.stdout.write(`${chalk.dim('Existing entities:')}\n`)
      for (const eid of existing) {
        const marker = eid === currentDef ? chalk.cyan(' (default)') : ''
        process.stdout.write(`  ${eid}${marker}\n`)
      }
      process.stdout.write('\n')
    }

    const rawId = await prompt(rl, '  Entity ID', { default: 'my-entity', hint: 'alphanumeric, hyphens' })
    const entityId = rawId.toLowerCase().replace(/\s+/g, '-')
    if (!entityId || entityId.includes('/') || entityId.includes('..')) {
      throw new CLIError('Invalid entity ID', 1)
    }

    const entityRoot = path.join(ENTITIES_DIR, entityId)
    const isExisting = existsSync(entityRoot)

    if (isExisting) {
      process.stdout.write(`\n${chalk.dim(`Existing entity at ${entityRoot}`)}\n\n`)
      const reset = await confirm(rl, '  Factory reset (wipe and re-init)?', false)
      if (!reset) {
        process.stdout.write(`\n${chalk.dim('Cancelled.')}\n\n`)
        return
      }

      // Wipe content but preserve .git
      const items = await fs.readdir(entityRoot, { withFileTypes: true })
      for (const item of items) {
        if (item.name === '.git') continue
        await fs.rm(path.join(entityRoot, item.name), { recursive: true, force: true })
      }
    }

    // ── Profile ──────────────────────────────────────────────────────────────
    const profiles = [
      { label: 'HACA-Core', description: 'Zero-autonomy, transparent topology' },
      { label: 'HACA-Evolve', description: 'Supervised autonomy, opaque topology' },
    ]
    const profileRes = await select(rl, 'Select profile:', profiles, 0)
    const profile: Profile = profileRes.index === 1 ? 'haca-evolve' : 'haca-core'
    const topology = profile === 'haca-evolve' ? 'opaque' : 'transparent'

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
    process.stdout.write(`\n${chalk.dim('Creating entity scaffold...')}\n`)
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
    process.stdout.write('\n')
    hr()
    info('Entity scaffold created')
    hr()
    process.stdout.write(`  ${chalk.dim('entity')}:   ${chalk.cyan(entityId)}\n`)
    process.stdout.write(`  ${chalk.dim('profile')}:  ${profile}\n`)
    process.stdout.write(`  ${chalk.dim('backend')}:  ${backend}\n`)
    if (authorizationScope) {
      const scope = [
        `evolution=${authorizationScope.autonomousEvolution}`,
        `skills=${authorizationScope.autonomousSkills}`,
        `memory=${authorizationScope.operatorMemory}`,
        `renewal=${authorizationScope.renewalDays}d`,
      ].join(' ')
      process.stdout.write(`  ${chalk.dim('scope')}:    ${scope}\n`)
    }
    process.stdout.write(`  ${chalk.dim('path')}:     ${entityRoot}\n`)
    hr()
    process.stdout.write(`\n${chalk.dim('First boot will run FAP (First Activation Protocol).')}\n`)
    process.stdout.write(`${chalk.dim('Run:')}  ${chalk.cyan('fcp')}\n\n`)

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
