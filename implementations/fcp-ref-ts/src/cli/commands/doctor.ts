// fcp doctor — compliance checker: verifies integrity doc, chain, and structure.
// --fix removes stale session tokens and restores missing skills index.
import * as path from 'node:path'
import * as os from 'node:os'
import * as fs from 'node:fs/promises'
import { existsSync } from 'node:fs'
import type { Command } from 'commander'
import { createLayout } from '../../types/store.js'
import { fileExists, readJson, writeJson } from '../../store/io.js'
import { verifyIntegrityDoc, verifyChainFromImprint, refreshIntegrityDoc } from '../../sil/sil.js'
import { CLIError } from '../../types/cli.js'

const ENTITIES_DIR = path.join(os.homedir(), '.fcp', 'entities')
const DEFAULT_FILE = path.join(os.homedir(), '.fcp', 'default')

interface CheckResult {
  name:     string
  status:   'pass' | 'warn' | 'fail'
  detail:   string
  fixable?: 'fixed' | 'unfixable'
  fixNote?: string
}

async function runChecks(root: string, fix: boolean): Promise<CheckResult[]> {
  const layout  = createLayout(root)
  const results: CheckResult[] = []

  function add(r: CheckResult) { results.push(r) }

  // 1. baseline.json present and parseable
  if (await fileExists(layout.state.baseline)) {
    try {
      await readJson(layout.state.baseline)
      add({ name: 'baseline.json', status: 'pass', detail: 'present and valid JSON' })
    } catch {
      add({ name: 'baseline.json', status: 'fail', detail: 'present but not valid JSON',
            fixable: 'unfixable', fixNote: 'run `fcp init` to reset' })
    }
  } else {
    add({ name: 'baseline.json', status: 'fail', detail: 'missing',
          fixable: 'unfixable', fixNote: 'run `fcp init` to create one' })
  }

  // 2. boot.md present
  if (await fileExists(layout.bootMd)) {
    add({ name: 'boot.md', status: 'pass', detail: 'present' })
  } else {
    add({ name: 'boot.md', status: 'warn', detail: 'missing — first boot will fail',
          fixable: 'unfixable', fixNote: 'restore manually then run `fcp init`' })
  }

  // 3. imprint.json
  if (await fileExists(layout.memory.imprint)) {
    add({ name: 'imprint.json', status: 'pass', detail: 'present (activated)' })
  } else {
    add({ name: 'imprint.json', status: 'warn', detail: 'absent — cold start pending' })
  }

  // 4. integrity.json drift check
  if (await fileExists(layout.state.integrity)) {
    const drift = await verifyIntegrityDoc(layout)
    if (drift.clean) {
      add({ name: 'integrity_doc', status: 'pass', detail: 'no drift detected' })
    } else {
      const summary = drift.mismatches.map(m => `${m.reason}:${m.file}`).join(', ')
      if (fix) {
        await refreshIntegrityDoc(layout)
        add({ name: 'integrity_doc', status: 'fail', detail: `drift was: ${summary}`,
              fixable: 'fixed', fixNote: 'integrity.json rehashed from current files' })
      } else {
        add({ name: 'integrity_doc', status: 'fail', detail: `drift detected: ${summary}`,
              fixNote: 'use --fix to rehash (only if you made the change intentionally)' })
      }
    }
  } else {
    add({ name: 'integrity_doc', status: 'warn', detail: 'integrity.json missing — run will regenerate' })
  }

  // 5. integrity chain
  if (await fileExists(layout.state.integrityChain)) {
    const chain = await verifyChainFromImprint(layout)
    if (chain.valid) {
      add({ name: 'integrity_chain', status: 'pass', detail: 'chain valid' })
    } else {
      add({ name: 'integrity_chain', status: 'fail', detail: `chain broken: ${chain.reason}`,
            fixable: 'unfixable', fixNote: 'chain history cannot be repaired — re-init required' })
    }
  } else {
    add({ name: 'integrity_chain', status: 'warn', detail: 'chain file absent (expected after first boot)' })
  }

  // 6. session token (stale check)
  if (await fileExists(layout.state.sentinels.sessionToken)) {
    let stale = false
    let detail = 'session is ACTIVE — another FCP instance may be running'
    try {
      const raw    = await readJson(layout.state.sentinels.sessionToken) as Record<string, unknown>
      const issued = new Date(raw['issuedAt'] as string).getTime()
      const age    = (Date.now() - issued) / 1000 / 60  // minutes
      if (age > 60) { stale = true; detail = `stale (${age.toFixed(0)}m old) — possible crash` }
    } catch {
      stale = true; detail = 'session token present but malformed'
    }

    if (stale && fix) {
      await fs.unlink(layout.state.sentinels.sessionToken)
      add({ name: 'session_token', status: 'warn', detail, fixable: 'fixed', fixNote: 'token removed' })
    } else {
      add({ name: 'session_token', status: 'warn', detail,
            ...(stale ? { fixable: 'unfixable' as const, fixNote: 'use --fix to remove it' } : {}) })
    }
  } else {
    add({ name: 'session_token', status: 'pass', detail: 'no active session' })
  }

  // 7. skills/index.json
  if (await fileExists(layout.skills.index)) {
    try {
      await readJson(layout.skills.index)
      add({ name: 'skills_index', status: 'pass', detail: 'present and valid JSON' })
    } catch {
      if (fix) {
        await writeJson(layout.skills.index, { version: '1.0', skills: [], aliases: {} })
        add({ name: 'skills_index', status: 'fail', detail: 'was malformed JSON',
              fixable: 'fixed', fixNote: 'reset to empty index' })
      } else {
        add({ name: 'skills_index', status: 'fail', detail: 'present but malformed JSON',
              fixable: 'unfixable' as const, fixNote: 'use --fix to reset to empty index' })
      }
    }
  } else {
    if (fix) {
      await writeJson(layout.skills.index, { version: '1.0', skills: [], aliases: {} })
      add({ name: 'skills_index', status: 'warn', detail: 'was missing',
            fixable: 'fixed', fixNote: 'created empty index' })
    } else {
      add({ name: 'skills_index', status: 'warn', detail: 'missing — will be generated at FAP',
            fixNote: 'use --fix to create empty index' })
    }
  }

  return results
}

async function runDoctor(entityId: string | undefined, fix: boolean): Promise<void> {
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

  const checks = await runChecks(root, fix)
  const fails  = checks.filter(c => c.status === 'fail' && c.fixable !== 'fixed').length
  const warns  = checks.filter(c => c.status === 'warn' && c.fixable !== 'fixed').length
  const fixed  = checks.filter(c => c.fixable === 'fixed').length

  process.stdout.write(`\n  fcp doctor — ${path.basename(root)}${fix ? '  (--fix)' : ''}\n  ${'─'.repeat(50)}\n`)
  for (const c of checks) {
    const icon = c.fixable === 'fixed' ? '⚡' : c.status === 'pass' ? '✓' : c.status === 'warn' ? '⚠' : '✗'
    const suffix = c.fixable === 'fixed'   ? `  → ${c.fixNote}`
                 : c.fixable === 'unfixable' && c.fixNote ? `  (${c.fixNote})`
                 : !fix && c.fixNote ? `  (${c.fixNote})`
                 : ''
    process.stdout.write(`  ${icon} ${c.name.padEnd(20)} ${c.detail}${suffix}\n`)
  }
  process.stdout.write(`  ${'─'.repeat(50)}\n`)
  if (fix && fixed > 0) {
    process.stdout.write(`  ${fixed} fixed, ${fails} failure(s), ${warns} warning(s)\n\n`)
  } else {
    process.stdout.write(`  ${fails} failure(s), ${warns} warning(s)\n\n`)
  }

  if (fails > 0) process.exit(1)
}

export function registerDoctor(program: Command): void {
  program
    .command('doctor')
    .description('Check entity integrity (uses default entity)')
    .option('--fix', 'Auto-fix recoverable issues (stale session token, missing skills index)')
    .action(async function (this: Command, opts: { fix?: boolean }) {
      const entity = (this.optsWithGlobals() as { entity?: string }).entity
      await runDoctor(entity, opts.fix === true)
    })
}
