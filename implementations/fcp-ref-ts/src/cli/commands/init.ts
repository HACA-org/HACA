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
  type PersonaProfile,
} from '../templates/integrity.js'
import { CLIError } from '../../types/cli.js'
import type { AuthorizationScope } from '../../types/formats/baseline.js'
import { prompt, select, hr, info, warn, header, UserCancelledError } from '../ui/prompt.js'

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
// Creates readline for the init flow. terminal:true is required so that readline
// properly manages stdin state after selectInteractive toggles raw mode.

function makeRl() {
  return createInterface({ input: process.stdin, output: process.stdout, terminal: true })
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

async function scaffoldEntity(root: string, profile: PersonaProfile): Promise<void> {
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
  const key = await prompt(rl, envVar, { hint: 'sk-...' })
  if (key) {
    existing.set(envVar, key)
    await writeEnvFile(existing)
    info(`Saved to ${chalk.dim('~/.fcp/.env')}`)
  } else {
    warn(`Skipped. Set ${envVar} in your shell or ~/.fcp/.env before running`)
  }
}

// ─── Step 4: CPE backend and model ────────────────────────────────────────────

async function pickBackend(rl: ReturnType<typeof makeRl>): Promise<string> {
  process.stdout.write('\n')
  hr('4. CPE backend and model')
  const providers = [
    { label: 'Anthropic', description: 'Claude models' },
    { label: 'OpenAI', description: 'GPT-4, o1 models' },
    { label: 'Google', description: 'Gemini models' },
    { label: 'Ollama', description: 'Local models' },
  ]

  const providerRes = await select(rl, 'Backend', providers)
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
      const manual = await prompt(rl, 'Model name', { default: 'llama3.2', hint: 'e.g., mistral, neural-chat' })
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
  process.stdout.write('\n')
  hr('3. Autonomous scope')
  process.stdout.write('  Define what this entity is authorised to do autonomously.\n')
  process.stdout.write('  These permissions can be revoked by re-initialising.\n')

  process.stdout.write('\n  [1] Autonomous structural evolution\n')
  process.stdout.write('      The entity may modify its own entity root freely, including\n')
  process.stdout.write('      its own code. WARNING: this grants unrestricted write access\n')
  process.stdout.write('      to the entire entity root.\n')
  const evolvRes = await select(rl, 'Authorise?', [
    { label: 'Yes' },
    { label: 'No' },
  ], 1)
  const autonomousEvolution = evolvRes.index === 0

  process.stdout.write('\n')
  process.stdout.write('  [2] Autonomous skill creation and installation\n')
  process.stdout.write('      The entity may create and install new skills without approval.\n')
  process.stdout.write('      WARNING: skills run as TypeScript code with full access to the\n')
  process.stdout.write('      entity root. Only enable if you trust the entity\'s judgment.\n')
  const skillsRes = await select(rl, 'Authorise?', [
    { label: 'Yes' },
    { label: 'No' },
  ], 1)
  const autonomousSkills = skillsRes.index === 0

  process.stdout.write('\n')
  process.stdout.write('  [3] Operator memory\n')
  process.stdout.write('      The entity may save your preferences and information across\n')
  process.stdout.write('      sessions. The entity will NEVER share your secrets (API keys,\n')
  process.stdout.write('      tokens, passwords). NOTE: you are also responsible for not\n')
  process.stdout.write('      sharing secrets directly in conversation — the entity cannot\n')
  process.stdout.write('      protect what it never receives.\n')
  const memoryRes = await select(rl, 'Authorise?', [
    { label: 'Yes' },
    { label: 'No' },
  ], 1)
  const operatorMemory = memoryRes.index === 0

  process.stdout.write('\n')
  process.stdout.write('  [4] Scope renewal interval\n')
  process.stdout.write('      These authorisations will expire and the entity will pause\n')
  process.stdout.write('      until you renew them.\n')
  let renewalDays = 0
  while (true) {
    const renewalInput = await prompt(rl, 'Renewal interval in days', { default: '30', hint: '0 to no expiry' })
    const parsed = Number(renewalInput)
    if (Number.isInteger(parsed) && parsed >= 0) {
      renewalDays = parsed
      break
    }
    warn('Please enter a non-negative integer.')
  }

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
    process.stdout.write('\n  FCP is a reference implementation of HACA and may contain\n')
    process.stdout.write('  errors. HACA is an open architecture specification for\n')
    process.stdout.write('  persistent cognitive entities.\n')
    process.stdout.write('\n  Contributions are welcome. Report issues and security\n')
    process.stdout.write('  vulnerabilities at: https://github.com/HACA-org/HACA\n')
    hr()
    process.stdout.write('\n')
    warn('WARNING: EXPERIMENTAL SYSTEM')
    hr()
    process.stdout.write('\n  Despite integrated safety mechanisms, this is experimental\n')
    process.stdout.write('  software. Use may result in data loss, host environment\n')
    process.stdout.write('  damage, or leakage of sensitive information.\n')
    process.stdout.write('\n  Do not use in production without a prior security review.\n')
    process.stdout.write('  By continuing, you acknowledge and accept these risks.\n')
    hr()
    process.stdout.write('\n')
    const continueRes = await select(rl, 'Continue?', [
      { label: 'Yes' },
      { label: 'No' },
    ], 1)
    if (continueRes.index === 1) {
      process.stdout.write(`\n${chalk.dim('Cancelled.')}\n\n`)
      return
    }
    process.stdout.write('\n')

    // ── Step 1: Entity ID ────────────────────────────────────────────────────
    process.stdout.write('\n')
    hr('1. Entity ID')
    process.stdout.write('\n  Entities are installed at ~/.fcp/<entity_id>/\n\n')

    const existing = await listEntities()
    const currentDef = await getDefault()
    if (existing.length > 0) {
      process.stdout.write(`  ${chalk.dim('Existing entities:')}\n`)
      for (const eid of existing) {
        const marker = eid === currentDef ? chalk.cyan(' (default)') : ''
        process.stdout.write(`    ${eid}${marker}\n`)
      }
      process.stdout.write('\n')
    }

    const rawId = await prompt(rl, 'Entity ID', { default: 'my-entity', hint: 'alphanumeric, hyphens' })
    const entityId = rawId.toLowerCase().replace(/\s+/g, '-')
    if (!entityId || !/^[a-z0-9][a-z0-9-]{0,62}$/.test(entityId)) {
      throw new CLIError('Invalid entity ID (use lowercase alphanumeric and hyphens, 1-63 chars)', 1)
    }

    const entityRoot = path.join(ENTITIES_DIR, entityId)
    const isExisting = existsSync(entityRoot)

    if (isExisting) {
      process.stdout.write(`\n  ${chalk.yellow('⚠')} Existing FCP entity detected at ${entityRoot}\n\n`)
      const actionRes = await select(rl, 'Select an action', [
        { label: 'Cancel' },
        { label: 'Factory reset — wipe entity root and re-initialise from scratch' },
      ], 1)
      const reset = actionRes.index === 1
      if (!reset) {
        process.stdout.write(`\n${chalk.dim('Cancelled.')}\n\n`)
        return
      }

      hr('Factory reset')
      process.stdout.write(`\n  Wiping ${entityRoot} ...\n`)
      // Wipe content but preserve .git
      const items = await fs.readdir(entityRoot, { withFileTypes: true })
      for (const item of items) {
        if (item.name === '.git') continue
        await fs.rm(path.join(entityRoot, item.name), { recursive: true, force: true })
      }
      info('Entity wiped. Re-initialising...')
      process.stdout.write('\n')
    }

    // ── Step 2: Profile ──────────────────────────────────────────────────────
    process.stdout.write('\n')
    hr('2. Profile')
    process.stdout.write('  HACA-Core — Zero-autonomy\n')
    process.stdout.write('    Every structural change and evolution requires explicit Operator\n')
    process.stdout.write('    approval. Designed for enterprise and adversarial environments.\n')
    process.stdout.write('\n')
    process.stdout.write('  HACA-Evolve — Supervised autonomy\n')
    process.stdout.write('    The entity acts and evolves independently within a declared scope,\n')
    process.stdout.write('    under Operator supervision. Designed for long-term assistants\n')
    process.stdout.write('    and companions.\n')
    process.stdout.write('\n')
    const profileRes = await select(rl, 'Profile', [
      { label: 'HACA-Core   — Zero-autonomy' },
      { label: 'HACA-Evolve — Supervised autonomy' },
    ], 0)
    const profile: PersonaProfile = profileRes.index === 1 ? 'haca-evolve' : 'haca-core'
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

    // Set as default
    await setDefault(entityId)

    // ── Step 5: Summary ─────────────────────────────────────────────────────
    process.stdout.write('\n')
    hr()
    info('Entity created successfully')
    hr()
    process.stdout.write(`  entity:         ${chalk.cyan(entityId)}\n`)
    process.stdout.write(`  path:           ${entityRoot}\n`)
    const profileVersion = profile === 'haca-evolve' ? 'HACA-Evolve-1.0.0' : 'HACA-Core-1.0.0'
    process.stdout.write(`  profile:        ${profileVersion}\n`)
    process.stdout.write(`  backend:        ${backend}\n`)
    if (authorizationScope) {
      process.stdout.write(`  scope:\n`)
      process.stdout.write(`    autonomous evolution:  ${authorizationScope.autonomousEvolution ? 'yes' : 'no'}\n`)
      process.stdout.write(`    autonomous skills:     ${authorizationScope.autonomousSkills ? 'yes' : 'no'}\n`)
      process.stdout.write(`    operator memory:       ${authorizationScope.operatorMemory ? 'yes' : 'no'}\n`)
      const renewal = authorizationScope.renewalDays
      process.stdout.write(`    renewal:               ${renewal > 0 ? `every ${renewal} days` : 'no expiry (0)'}\n`)
    }
    hr()
    process.stdout.write('\n  First boot will run FAP (First Activation Protocol).\n')
    process.stdout.write(`  Run:  ${chalk.cyan('fcp')}\n\n`)

  } finally {
    // Ensure terminal state is restored even on crash
    try { process.stdin.setRawMode?.(false) } catch { /* ignore */ }
    process.stdout.write('\x1b[?25h') // Ensure cursor is visible
    rl.close()
  }
}

export function registerInit(program: Command): void {
  program
    .command('init')
    .description('Install or reset an FCP entity')
    .action(async () => {
      try {
        await runInit()
      } catch (err) {
        if (err instanceof UserCancelledError) {
          process.stdout.write(`\n${chalk.dim('Cancelled.')}\n\n`)
          process.exit(0)
        }
        throw err
      }
    })
}
