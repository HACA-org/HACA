// fcp doctor — compliance checker: verifies integrity doc, chain, and structure.
import * as path from 'node:path'
import * as os from 'node:os'
import * as fs from 'node:fs/promises'
import { existsSync } from 'node:fs'
import type { Command } from 'commander'
import { createLayout } from '../../types/store.js'
import { fileExists, readJson } from '../../store/io.js'
import { verifyIntegrityDoc, verifyChainFromImprint } from '../../sil/integrity.js'
import { CLIError } from '../../types/cli.js'

const ENTITIES_DIR = path.join(os.homedir(), '.fcp', 'entities')
const DEFAULT_FILE = path.join(os.homedir(), '.fcp', 'default')

interface CheckResult {
  name:   string
  status: 'pass' | 'warn' | 'fail'
  detail: string
}

async function runChecks(root: string): Promise<CheckResult[]> {
  const layout  = createLayout(root)
  const results: CheckResult[] = []

  function add(name: string, status: 'pass' | 'warn' | 'fail', detail: string) {
    results.push({ name, status, detail })
  }

  // 1. baseline.json present and parseable
  if (await fileExists(layout.state.baseline)) {
    try {
      await readJson(layout.state.baseline)
      add('baseline.json', 'pass', 'present and valid JSON')
    } catch {
      add('baseline.json', 'fail', 'present but not valid JSON')
    }
  } else {
    add('baseline.json', 'fail', 'missing')
  }

  // 2. boot.md present
  if (await fileExists(layout.bootMd)) {
    add('boot.md', 'pass', 'present')
  } else {
    add('boot.md', 'warn', 'missing — first boot will fail')
  }

  // 3. imprint.json
  if (await fileExists(layout.memory.imprint)) {
    add('imprint.json', 'pass', 'present (activated)')
  } else {
    add('imprint.json', 'warn', 'absent — cold start pending')
  }

  // 4. integrity.json drift check
  if (await fileExists(layout.state.integrity)) {
    const drift = await verifyIntegrityDoc(layout)
    if (drift.clean) {
      add('integrity_doc', 'pass', 'no drift detected')
    } else {
      const summary = drift.mismatches.map(m => `${m.reason}:${m.file}`).join(', ')
      add('integrity_doc', 'fail', `drift detected: ${summary}`)
    }
  } else {
    add('integrity_doc', 'warn', 'integrity.json missing — run will regenerate')
  }

  // 5. integrity chain
  if (await fileExists(layout.state.integrityChain)) {
    const chain = await verifyChainFromImprint(layout)
    if (chain.valid) {
      add('integrity_chain', 'pass', 'chain valid')
    } else {
      add('integrity_chain', 'fail', `chain broken: ${chain.reason}`)
    }
  } else {
    add('integrity_chain', 'warn', 'chain file absent (expected after first boot)')
  }

  // 6. session token (stale check)
  if (await fileExists(layout.state.sentinels.sessionToken)) {
    try {
      const raw = await readJson(layout.state.sentinels.sessionToken) as Record<string, unknown>
      const issued = new Date(raw['issuedAt'] as string).getTime()
      const age    = (Date.now() - issued) / 1000 / 60  // minutes
      if (age > 60) {
        add('session_token', 'warn', `stale (${age.toFixed(0)}m old) — possible crash`)
      } else {
        add('session_token', 'warn', 'session is ACTIVE — another FCP instance may be running')
      }
    } catch {
      add('session_token', 'warn', 'session.token present but malformed')
    }
  } else {
    add('session_token', 'pass', 'no active session')
  }

  // 7. skills/index.json
  if (await fileExists(layout.skills.index)) {
    try {
      await readJson(layout.skills.index)
      add('skills_index', 'pass', 'present and valid JSON')
    } catch {
      add('skills_index', 'fail', 'present but malformed JSON')
    }
  } else {
    add('skills_index', 'warn', 'missing — will be generated at FAP')
  }

  return results
}

async function runDoctor(entityId?: string): Promise<void> {
  let root: string

  if (entityId) {
    root = path.join(ENTITIES_DIR, entityId)
    if (!existsSync(root)) throw new CLIError(`Entity not found: ${entityId}`, 1)
  } else {
    const defaultId = existsSync(DEFAULT_FILE)
      ? (await fs.readFile(DEFAULT_FILE, 'utf8')).trim()
      : null

    if (defaultId) {
      root = path.join(ENTITIES_DIR, defaultId)
    } else if (existsSync(ENTITIES_DIR)) {
      const entries = await fs.readdir(ENTITIES_DIR, { withFileTypes: true })
      const dirs    = entries.filter(e => e.isDirectory())
      if (dirs.length === 0) throw new CLIError('No entities found. Run `fcp init`.', 1)
      root = path.join(ENTITIES_DIR, dirs[0]!.name)
    } else {
      throw new CLIError('No entities found. Run `fcp init`.', 1)
    }
  }

  const checks  = await runChecks(root)
  const fails   = checks.filter(c => c.status === 'fail').length
  const warns   = checks.filter(c => c.status === 'warn').length

  process.stdout.write(`\n  fcp doctor — ${path.basename(root)}\n  ${'─'.repeat(50)}\n`)
  for (const c of checks) {
    const icon = c.status === 'pass' ? '✓' : c.status === 'warn' ? '⚠' : '✗'
    process.stdout.write(`  ${icon} ${c.name.padEnd(20)} ${c.detail}\n`)
  }
  process.stdout.write(`  ${'─'.repeat(50)}\n`)
  process.stdout.write(`  ${fails} failure(s), ${warns} warning(s)\n\n`)

  if (fails > 0) process.exit(1)
}

export function registerDoctor(program: Command): void {
  program
    .command('doctor [entity]')
    .description('Check entity compliance and integrity')
    .action(async (entity?: string) => {
      await runDoctor(entity)
    })
}
