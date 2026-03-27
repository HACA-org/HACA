// fcp init — interactive entity scaffolding.
// Separates interactive flow (readline prompts) from file generation (templates/).
import * as path from 'node:path'
import * as os from 'node:os'
import * as fs from 'node:fs/promises'
import { existsSync } from 'node:fs'
import { createInterface } from 'node:readline'
import type { Command } from 'commander'
import { writeJson, ensureDir, atomicWrite } from '../../store/io.js'
import { makeBaselineJson } from '../templates/baseline.js'
import {
  makeIntegrityDoc, personaIdentity, personaValues,
  personaConstraints, personaProtocol, bootMd, GITIGNORE,
  type Profile,
} from '../templates/integrity.js'
import { CLIError } from '../../types/cli.js'

const FCP_HOME     = path.join(os.homedir(), '.fcp')
const ENTITIES_DIR = path.join(FCP_HOME, 'entities')
const DEFAULT_FILE = path.join(FCP_HOME, 'default')

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
    const existing     = await listEntities()
    const currentDef   = await getDefault()
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
    const isExisting = existsSync(path.join(entityRoot, 'state', 'baseline.json'))

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

    // ── Backend ──────────────────────────────────────────────────────────────
    hr('CPE Backend')
    process.stdout.write('\n  Format: <provider>:<model>\n')
    process.stdout.write(  '  Examples: anthropic:claude-opus-4-6  openai:gpt-4o  ollama:llama3.2\n\n')
    const backend = await ask(rl, '  Backend', 'anthropic:claude-sonnet-4-6')

    // ── Operator credentials ─────────────────────────────────────────────────
    hr('Operator')
    const operatorName  = await ask(rl, '  Name',  os.userInfo().username)
    const operatorEmail = await ask(rl, '  Email', `${os.userInfo().username}@localhost`)

    // ── Budget ───────────────────────────────────────────────────────────────
    const budgetTokens = 200_000

    // ── Scaffold ─────────────────────────────────────────────────────────────
    hr('Creating entity')
    process.stdout.write('\n')

    await scaffoldEntity(entityRoot, profile)
    await writeJson(path.join(entityRoot, 'state', 'baseline.json'), makeBaselineJson({
      entityId, topology, backend, budgetTokens,
    }))

    // Store operator credentials for FAP as a staging file (read by init, cleared by FAP)
    await writeJson(path.join(entityRoot, 'state', '.fap-operator.json'), {
      operator_name: operatorName, operator_email: operatorEmail,
    })

    // Set default if none
    if (!currentDef) await setDefault(entityId)

    // ── Summary ──────────────────────────────────────────────────────────────
    process.stdout.write('  Entity scaffold created.\n')
    hr()
    process.stdout.write(`  entity:   ${entityId}\n`)
    process.stdout.write(`  path:     ${entityRoot}\n`)
    process.stdout.write(`  profile:  ${profile}\n`)
    process.stdout.write(`  backend:  ${backend}\n`)
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
