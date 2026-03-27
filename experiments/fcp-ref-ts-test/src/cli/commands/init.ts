import { join } from 'node:path'
import { existsSync } from 'node:fs'
import { mkdir, rm, writeFile, readdir } from 'node:fs/promises'
import { homedir } from 'node:os'
import { createInterface } from 'node:readline'
import type { Command } from 'commander'
import { detectAvailableModels } from '../../cpe/cpe.js'
import { writeJson } from '../../store/io.js'
import {
  makeBaseline,
  PERSONA_IDENTITY_CORE,
  PERSONA_IDENTITY_EVOLVE,
  PERSONA_VALUES_CORE,
  PERSONA_VALUES_EVOLVE,
  PERSONA_CONSTRAINTS_CORE,
  PERSONA_CONSTRAINTS_EVOLVE,
  PERSONA_PROTOCOL,
  BOOT_MD,
  GITIGNORE,
  type EvolveScope,
} from '../templates.js'

const FCP_HOME = join(homedir(), '.fcp')
const ENTITIES_DIR = join(FCP_HOME, 'entities')
const DEFAULT_FILE = join(FCP_HOME, 'default')

// ─── Readline helpers ─────────────────────────────────────────────────────────

function makeRl() {
  return createInterface({ input: process.stdin, output: process.stdout })
}

function ask(rl: ReturnType<typeof makeRl>, question: string, defaultVal = ''): Promise<string> {
  return new Promise(resolve => {
    const prompt = defaultVal ? `${question} [${defaultVal}]: ` : `${question}: `
    rl.question(prompt, answer => {
      resolve(answer.trim() || defaultVal)
    })
  })
}

function confirm(rl: ReturnType<typeof makeRl>, question: string, defaultYes = true): Promise<boolean> {
  return new Promise(resolve => {
    const hint = defaultYes ? 'Y/n' : 'y/N'
    rl.question(`${question} [${hint}]: `, answer => {
      const a = answer.trim().toLowerCase()
      if (a === '') resolve(defaultYes)
      else resolve(a === 'y' || a === 'yes')
    })
  })
}

async function pickOne(
  rl: ReturnType<typeof makeRl>,
  label: string,
  items: string[],
  defaultIdx = 0,
): Promise<number> {
  console.log(`\n  ${label}:`)
  items.forEach((item, i) => {
    const marker = i === defaultIdx ? '>' : ' '
    console.log(`  ${marker} [${i + 1}] ${item}`)
  })
  while (true) {
    const answer = await ask(rl, `  Choice`, String(defaultIdx + 1))
    const n = parseInt(answer, 10)
    if (!isNaN(n) && n >= 1 && n <= items.length) return n - 1
    console.log(`  Please enter a number between 1 and ${items.length}.`)
  }
}

// ─── Entity registry helpers ──────────────────────────────────────────────────

async function listEntities(): Promise<string[]> {
  if (!existsSync(ENTITIES_DIR)) return []
  const entries = await readdir(ENTITIES_DIR, { withFileTypes: true })
  return entries.filter(e => e.isDirectory()).map(e => e.name)
}

async function getDefaultEntity(): Promise<string | null> {
  if (!existsSync(DEFAULT_FILE)) return null
  const { readFile } = await import('node:fs/promises')
  const content = (await readFile(DEFAULT_FILE, 'utf8')).trim()
  return content || null
}

async function setDefaultEntity(id: string): Promise<void> {
  await mkdir(FCP_HOME, { recursive: true })
  await writeFile(DEFAULT_FILE, id + '\n', 'utf8')
}

// ─── Scaffold helpers ─────────────────────────────────────────────────────────

async function scaffoldDirs(root: string): Promise<void> {
  const dirs = [
    join(root, 'memory', 'episodic'),
    join(root, 'memory', 'semantic'),
    join(root, 'memory', 'active_context'),
    join(root, 'state'),
    join(root, 'io', 'inbox', 'presession'),
    join(root, 'io', 'spool'),
    join(root, 'io', 'notifications'),
    join(root, 'persona'),
    join(root, 'skills'),
    join(root, 'hooks'),
  ]
  for (const d of dirs) {
    await mkdir(d, { recursive: true })
  }
}

async function writePersona(root: string, profile: 'haca-core' | 'haca-evolve'): Promise<void> {
  const dir = join(root, 'persona')
  const isEvolve = profile === 'haca-evolve'

  await writeFile(join(dir, 'identity.md'), isEvolve ? PERSONA_IDENTITY_EVOLVE : PERSONA_IDENTITY_CORE, 'utf8')
  await writeFile(join(dir, 'values.md'), isEvolve ? PERSONA_VALUES_EVOLVE : PERSONA_VALUES_CORE, 'utf8')
  await writeFile(join(dir, 'constraints.md'), isEvolve ? PERSONA_CONSTRAINTS_EVOLVE : PERSONA_CONSTRAINTS_CORE, 'utf8')
  await writeFile(join(dir, 'protocol.md'), PERSONA_PROTOCOL, 'utf8')
}

async function writeStateFiles(root: string): Promise<void> {
  await writeFile(join(root, 'memory', 'session.jsonl'), '', 'utf8')
  await writeJson(join(root, 'memory', 'working-memory.json'), { entries: [] })
  await writeJson(join(root, 'state', 'integrity.json'), {
    version: '1.0', algorithm: 'sha256',
    last_checkpoint: null, files: {},
  })
  await writeFile(join(root, 'state', 'integrity-chain.jsonl'), '', 'utf8')
}

async function gitInit(root: string, entityId: string, profile: string): Promise<boolean> {
  const { execFile } = await import('node:child_process')
  const { promisify } = await import('node:util')
  const exec = promisify(execFile)

  try {
    await exec('git', ['init', root])
    await writeFile(join(root, '.gitignore'), GITIGNORE, 'utf8')
    await exec('git', ['-C', root, 'add', '.'])
    await exec('git', ['-C', root, 'commit', '-m', `chore: init entity ${entityId} (${profile})`])
    return true
  } catch {
    return false
  }
}

// ─── hr / ui helpers ──────────────────────────────────────────────────────────

function hr(label = '') {
  const line = '─'.repeat(60)
  if (label) {
    console.log(`\n  ── ${label} ${'─'.repeat(Math.max(0, 54 - label.length))}`)
  } else {
    console.log(`  ${line}`)
  }
}

// ─── Main ─────────────────────────────────────────────────────────────────────

async function runInit(opts: { reset?: boolean }): Promise<void> {
  if (!process.stdin.isTTY) {
    console.log('fcp init — requires an interactive terminal')
    return
  }

  const rl = makeRl()

  try {
    console.log()
    hr()
    console.log('  fcp-ref-lite — Filesystem Cognitive Platform')
    console.log('  HACA — Host-Agnostic Cognitive Architecture v1.0')
    hr()
    console.log('  This is experimental software. Use may result in data loss,')
    console.log('  environment damage, or leakage of sensitive information.')
    console.log('  Do not use in production without a prior security review.')
    hr()
    console.log()

    const proceed = await confirm(rl, '  Continue?', true)
    if (!proceed) { rl.close(); return }

    // ── Step 1: Entity ID ───────────────────────────────────────────────────
    hr('1. Entity ID')
    console.log()
    console.log(`  Entities are installed at ${ENTITIES_DIR}/<entity_id>/`)
    console.log()

    const existing = await listEntities()
    const currentDefault = await getDefaultEntity()
    if (existing.length > 0) {
      console.log('  Existing entities:')
      for (const eid of existing) {
        const marker = eid === currentDefault ? '  (default)' : ''
        console.log(`    ${eid}${marker}`)
      }
      console.log()
    }

    const rawId = await ask(rl, '  Entity ID', 'my-entity')
    const entityId = rawId.toLowerCase().replace(/\s+/g, '-')
    if (!entityId || entityId.includes('/') || entityId.includes('\\') || entityId.includes('..')) {
      console.error('  Invalid entity ID.')
      rl.close()
      process.exit(1)
    }

    const entityRoot = join(ENTITIES_DIR, entityId)
    const isExisting = existsSync(join(entityRoot, 'state', 'baseline.json'))
      || existsSync(join(entityRoot, '.fcp-entity'))

    if (isExisting && !opts.reset) {
      console.log()
      console.log(`  Existing entity detected at ${entityRoot}.`)
      const resetIdx = await pickOne(rl, 'Select an action', [
        'Factory reset — wipe and re-initialise',
        'Cancel',
      ], 1)
      if (resetIdx === 1) { rl.close(); return }

      hr('Factory reset')
      console.log()
      console.log(`  Wiping ${entityRoot} ...`)
      const items = await readdir(entityRoot, { withFileTypes: true })
      for (const item of items) {
        if (item.name === '.git') continue
        const fullPath = join(entityRoot, item.name)
        await rm(fullPath, { recursive: true, force: true })
      }
      console.log('  Done.')
    }

    // ── Step 2: Profile ─────────────────────────────────────────────────────
    hr('2. Profile')
    console.log()
    console.log('  HACA-Core   — Zero-autonomy. Every structural change requires')
    console.log('                explicit Operator approval.')
    console.log()
    console.log('  HACA-Evolve — Supervised autonomy. The entity acts and evolves')
    console.log('                independently within a declared scope.')
    console.log()

    const profileIdx = await pickOne(rl, 'Profile', [
      'HACA-Core   — Zero-autonomy',
      'HACA-Evolve — Supervised autonomy',
    ], 0)
    const profile: 'haca-core' | 'haca-evolve' = profileIdx === 0 ? 'haca-core' : 'haca-evolve'

    // ── Step 3: Evolve scope ─────────────────────────────────────────────────
    let evolveScope: EvolveScope | undefined

    if (profile === 'haca-evolve') {
      hr('3. Autonomous scope')
      console.log()
      console.log('  Define what this entity is authorised to do autonomously.')
      console.log()

      console.log('  [1] Autonomous structural evolution')
      console.log('      Grants unrestricted write access to the entity root.')
      const allowEvolution = await confirm(rl, '      Authorise?', false)

      console.log()
      console.log('  [2] Autonomous skill creation and installation')
      console.log('      Skills run as code with full entity root access.')
      const allowSkills = await confirm(rl, '      Authorise?', false)

      console.log()
      console.log('  [3] Cognitive Mesh Interface (CMI) access')
      const cmiIdx = await pickOne(rl, 'CMI access', [
        'none    — No CMI access',
        'private — Private channels only',
        'public  — Public channels only',
        'both    — Private and public channels',
      ], 0)
      const cmiOptions = ['none', 'private', 'public', 'both'] as const
      const cmiAccess = cmiOptions[cmiIdx]!

      console.log()
      console.log('  [4] Operator memory')
      console.log('      The entity may save preferences across sessions.')
      const allowMemory = await confirm(rl, '      Authorise?', true)

      console.log()
      console.log('  [5] Scope renewal interval (0 = disabled)')
      let renewalDays = 30
      while (true) {
        const raw = await ask(rl, '      Renewal interval in days', '30')
        const n = parseInt(raw, 10)
        if (!isNaN(n) && n >= 0) { renewalDays = n; break }
        console.log('      Please enter a non-negative integer.')
      }

      evolveScope = {
        structural_evolution: allowEvolution,
        skill_management: allowSkills,
        cmi_access: cmiAccess,
        operator_memory: allowMemory,
        renewal_days: renewalDays,
      }
    }

    // ── Step 4: CPE backend and model ────────────────────────────────────────
    hr('4. CPE backend and model')
    console.log()
    console.log('  Detecting available providers...')

    const available = await detectAvailableModels()

    let provider: string
    let model: string

    if (available.length === 0) {
      console.log('  No providers detected. Configuring manually.')
      console.log()
      provider = await ask(rl, '  Provider (anthropic/google/openai/ollama)', 'anthropic')
      model = await ask(rl, '  Model', 'claude-sonnet-4-6')
    } else {
      const labels = available.map(m => `${m.provider} / ${m.id}`)
      const idx = await pickOne(rl, 'Model', labels, 0)
      const chosen = available[idx]!
      provider = chosen.provider
      model = chosen.id
    }

    // ── Step 5: Create entity ────────────────────────────────────────────────
    hr('5. Creating entity')
    console.log()

    await scaffoldDirs(entityRoot)
    await writePersona(entityRoot, profile)
    await writeFile(join(entityRoot, 'BOOT.md'), BOOT_MD, 'utf8')
    await writeStateFiles(entityRoot)

    const baseline = makeBaseline({
      entityId, profile, provider, model,
      ...(evolveScope !== undefined ? { evolveScope } : {}),
    })
    await writeJson(join(entityRoot, 'state', 'baseline.json'), baseline)

    await writeJson(join(entityRoot, '.fcp-entity'), {
      version: '0.1.0',
      profile,
      created_at: new Date().toISOString(),
    })

    await writeJson(join(entityRoot, 'skills', 'index.json'), { skills: [] })

    console.log('  Entity scaffold created.')

    // ── Git init ─────────────────────────────────────────────────────────────
    let gitOk = false
    if (!existsSync(join(entityRoot, '.git'))) {
      const doGit = await confirm(rl, '\n  Initialise a git repository in the entity root?', true)
      if (doGit) {
        gitOk = await gitInit(entityRoot, entityId, profile)
        if (!gitOk) console.log('  [!] git init failed — skipping.')
      }
    }

    // ── Step 7: Set default ──────────────────────────────────────────────────
    const wasDefault = currentDefault === entityId
    if (!currentDefault) {
      await setDefaultEntity(entityId)
    }

    // ── Step 8: Summary ──────────────────────────────────────────────────────
    console.log()
    hr()
    console.log('  Entity created successfully')
    hr()
    console.log(`  entity:    ${entityId}`)
    console.log(`  path:      ${entityRoot}`)
    console.log(`  profile:   ${profile}`)
    console.log(`  backend:   ${provider} / ${model}`)
    if (gitOk) console.log('  git:       initial commit created')
    if (profile === 'haca-evolve' && evolveScope) {
      console.log('  scope:')
      console.log(`    structural evolution:  ${evolveScope.structural_evolution ? 'yes' : 'no'}`)
      console.log(`    skill management:      ${evolveScope.skill_management ? 'yes' : 'no'}`)
      console.log(`    cmi access:            ${evolveScope.cmi_access}`)
      console.log(`    operator memory:       ${evolveScope.operator_memory ? 'yes' : 'no'}`)
      console.log(`    renewal:               ${evolveScope.renewal_days > 0 ? `every ${evolveScope.renewal_days} days` : 'disabled'}`)
    }
    hr()
    console.log()
    console.log('  First boot will run FAP (First Activation Protocol).')
    if (!currentDefault || wasDefault) {
      console.log('  Run:  fcp')
    } else {
      console.log(`  Run:  fcp set ${entityId} && fcp`)
    }
    console.log()

  } finally {
    rl.close()
  }
}

export function registerInit(program: Command): void {
  program
    .command('init')
    .description('Install or reset an entity')
    .option('--reset', 'Skip existing-entity prompt and force factory reset')
    .action(async (opts: { reset?: boolean }) => {
      await runInit(opts)
    })
}
