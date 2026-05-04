// fcp doctor — entity health & integrity validator.
// Validates structure, schemas, integrity doc, chain linkage, and runtime state.
// --fix resolves recoverable issues: rehashes integrity doc, removes stale tokens,
// restores missing skills index, recreates missing directories.
import * as path from 'node:path'
import * as fs from 'node:fs/promises'
import { existsSync } from 'node:fs'
import type { Command } from 'commander'
import { createLayout } from '../../types/store.js'
import { fileExists, readJson, writeJson } from '../../store/io.js'
import { verifyIntegrityDoc, verifyChainFromImprint, refreshIntegrityDoc } from '../../sil/sil.js'
import { parseBaseline, parseImprintRecord, ParseError } from '../../store/parse.js'
import { sha256Digest } from '../../boot/integrity.js'
import { CLIError } from '../../types/cli.js'
import { resolveEntityRoot } from '../entity.js'

interface CheckResult {
  name:     string
  status:   'pass' | 'warn' | 'fail'
  detail:   string
  fixable?: 'fixed' | 'unfixable'
  fixNote?: string
}

// ─── individual checks ───────────────────────────────────────────────────────

type CheckFn = (root: string, fix: boolean) => Promise<CheckResult[]>

// 1. Directory structure — required dirs must exist.
const checkStructure: CheckFn = async (root, fix) => {
  const layout  = createLayout(root)
  const results: CheckResult[] = []
  const required = [
    { label: 'state/',   path: layout.state.dir },
    { label: 'memory/',  path: layout.memory.dir },
    { label: 'persona/', path: layout.persona },
    { label: 'skills/',  path: layout.skills.dir },
    { label: 'io/',      path: layout.io.inbox },
  ]
  for (const dir of required) {
    if (existsSync(dir.path)) {
      results.push({ name: `dir:${dir.label}`, status: 'pass', detail: 'exists' })
    } else if (fix) {
      await fs.mkdir(dir.path, { recursive: true })
      results.push({ name: `dir:${dir.label}`, status: 'warn', detail: 'was missing',
        fixable: 'fixed', fixNote: 'created' })
    } else {
      results.push({ name: `dir:${dir.label}`, status: 'fail', detail: 'missing',
        fixNote: 'use --fix to create, or run `fcp init`' })
    }
  }
  return results
}

// 2. baseline.json — must exist, be valid JSON, and pass Zod schema.
const checkBaseline: CheckFn = async (root) => {
  const layout = createLayout(root)
  if (!await fileExists(layout.state.baseline)) {
    return [{ name: 'baseline.json', status: 'fail', detail: 'missing',
      fixable: 'unfixable', fixNote: 'run `fcp init` to create' }]
  }
  try {
    const raw = await readJson(layout.state.baseline)
    parseBaseline(raw)
    return [{ name: 'baseline.json', status: 'pass', detail: 'valid schema' }]
  } catch (e) {
    const msg = e instanceof ParseError ? e.cause.issues.map(i => i.message).join('; ') : 'invalid JSON'
    return [{ name: 'baseline.json', status: 'fail', detail: msg,
      fixable: 'unfixable', fixNote: 'fix manually or run `fcp init` to recreate' }]
  }
}

// 3. boot.md
const checkBootMd: CheckFn = async (root) => {
  const layout = createLayout(root)
  if (await fileExists(layout.bootMd)) {
    return [{ name: 'boot.md', status: 'pass', detail: 'present' }]
  }
  return [{ name: 'boot.md', status: 'warn', detail: 'missing — boot will fail',
    fixable: 'unfixable', fixNote: 'run `fcp init` to regenerate' }]
}

// 4. persona files — identity.md, values.md, constraints.md, protocol.md
const PERSONA_FILES = ['identity.md', 'values.md', 'constraints.md', 'protocol.md']

const checkPersona: CheckFn = async (root) => {
  const layout  = createLayout(root)
  const results: CheckResult[] = []
  for (const f of PERSONA_FILES) {
    const fp = path.join(layout.persona, f)
    if (await fileExists(fp)) {
      results.push({ name: `persona/${f}`, status: 'pass', detail: 'present' })
    } else {
      results.push({ name: `persona/${f}`, status: 'warn', detail: 'missing',
        fixNote: 'run `fcp init` to regenerate' })
    }
  }
  return results
}

// 5. imprint.json — presence, schema validation, operator hash cross-check.
const checkImprint: CheckFn = async (root) => {
  const layout = createLayout(root)
  if (!await fileExists(layout.memory.imprint)) {
    return [{ name: 'imprint.json', status: 'warn', detail: 'absent — entity not yet activated (cold start pending)' }]
  }
  try {
    const raw     = await readJson(layout.memory.imprint)
    const imprint = parseImprintRecord(raw)

    // Cross-check: verify operator hash = sha256(name + "\n" + email)
    const { operatorName, operatorEmail, operatorHash } = imprint.operatorBound
    const expected = sha256Digest(operatorName + '\n' + operatorEmail)
    if (operatorHash !== expected) {
      return [{ name: 'imprint.json', status: 'fail',
        detail: `operator hash mismatch — expected ${expected.slice(0, 20)}…, got ${operatorHash.slice(0, 20)}…`,
        fixable: 'unfixable', fixNote: 'imprint is sealed; re-init required' }]
    }

    return [{ name: 'imprint.json', status: 'pass', detail: `activated — ${imprint.hacaProfile}` }]
  } catch (e) {
    const msg = e instanceof ParseError ? e.cause.issues.map(i => i.message).join('; ') : 'invalid JSON'
    return [{ name: 'imprint.json', status: 'fail', detail: `malformed: ${msg}`,
      fixable: 'unfixable', fixNote: 'imprint is sealed; re-init required' }]
  }
}

// 6. integrity.json — drift detection (bidirectional: hash mismatches + untracked files).
const checkIntegrityDoc: CheckFn = async (root, fix) => {
  const layout = createLayout(root)
  if (!await fileExists(layout.state.integrity)) {
    return [{ name: 'integrity_doc', status: 'warn', detail: 'missing — will be generated at next boot' }]
  }

  const drift = await verifyIntegrityDoc(layout)
  if (drift.clean) {
    return [{ name: 'integrity_doc', status: 'pass', detail: 'all hashes match' }]
  }

  // Build detailed per-file report.
  const lines: string[] = []
  for (const m of drift.mismatches) {
    if (m.reason === 'hash_mismatch') {
      lines.push(`  ${m.file}: hash mismatch (expected ${m.expected!.slice(0, 12)}…, got ${m.actual!.slice(0, 12)}…)`)
    } else if (m.reason === 'missing') {
      lines.push(`  ${m.file}: file missing from disk`)
    } else if (m.reason === 'untracked') {
      lines.push(`  ${m.file}: on disk but not in integrity.json`)
    }
  }
  const detail = `${drift.mismatches.length} file(s) drifted:\n${lines.join('\n')}`

  if (fix) {
    await refreshIntegrityDoc(layout)
    return [{ name: 'integrity_doc', status: 'fail', detail,
      fixable: 'fixed', fixNote: 'integrity.json rehashed from current files' }]
  }
  return [{ name: 'integrity_doc', status: 'fail', detail,
    fixNote: 'use --fix to rehash' }]
}

// 7. integrity chain — genesis + prevHash linkage.
const checkIntegrityChain: CheckFn = async (root) => {
  const layout = createLayout(root)
  if (!await fileExists(layout.state.integrityChain)) {
    return [{ name: 'integrity_chain', status: 'warn', detail: 'absent (expected before first evolution)' }]
  }
  const result = await verifyChainFromImprint(layout)
  if (result.valid) {
    return [{ name: 'integrity_chain', status: 'pass', detail: 'chain linkage valid' }]
  }
  return [{ name: 'integrity_chain', status: 'fail', detail: `broken: ${result.reason}`,
    fixable: 'unfixable', fixNote: 'chain cannot be repaired — re-init required' }]
}

// 8. session token — stale detection.
const checkSessionToken: CheckFn = async (root, fix) => {
  const layout = createLayout(root)
  if (!await fileExists(layout.state.sentinels.sessionToken)) {
    return [{ name: 'session_token', status: 'pass', detail: 'no active session' }]
  }

  let stale  = false
  let detail = 'session ACTIVE — another FCP instance may be running'
  try {
    const raw    = await readJson(layout.state.sentinels.sessionToken) as Record<string, unknown>
    const issued = new Date(raw['issuedAt'] as string).getTime()
    const ageMin = (Date.now() - issued) / 1000 / 60
    if (ageMin > 60) {
      stale  = true
      detail = `stale token (${ageMin.toFixed(0)}m old) — likely crashed session`
    }
  } catch {
    stale  = true
    detail = 'token present but malformed'
  }

  if (stale && fix) {
    await fs.unlink(layout.state.sentinels.sessionToken)
    return [{ name: 'session_token', status: 'warn', detail, fixable: 'fixed', fixNote: 'token removed' }]
  }
  return [{ name: 'session_token', status: stale ? 'warn' : 'pass', detail,
    ...(stale ? { fixNote: 'use --fix to remove stale token' } : {}) }]
}

// 9. skills/index.json — presence + valid JSON.
const checkSkillsIndex: CheckFn = async (root, fix) => {
  const layout = createLayout(root)
  if (await fileExists(layout.skills.index)) {
    try {
      await readJson(layout.skills.index)
      return [{ name: 'skills_index', status: 'pass', detail: 'valid JSON' }]
    } catch {
      if (fix) {
        await writeJson(layout.skills.index, { version: '1.0', skills: [], aliases: {} })
        return [{ name: 'skills_index', status: 'fail', detail: 'was malformed',
          fixable: 'fixed', fixNote: 'reset to empty index' }]
      }
      return [{ name: 'skills_index', status: 'fail', detail: 'malformed JSON',
        fixNote: 'use --fix to reset' }]
    }
  }

  if (fix) {
    await writeJson(layout.skills.index, { version: '1.0', skills: [], aliases: {} })
    return [{ name: 'skills_index', status: 'warn', detail: 'was missing',
      fixable: 'fixed', fixNote: 'created empty index' }]
  }
  return [{ name: 'skills_index', status: 'warn', detail: 'missing',
    fixNote: 'use --fix to create' }]
}

// 10. allowlist.json — presence + valid JSON.
const checkAllowlist: CheckFn = async (root) => {
  const layout = createLayout(root)
  if (!await fileExists(layout.state.allowlist)) {
    return [{ name: 'allowlist.json', status: 'warn', detail: 'missing — default deny-all applies' }]
  }
  try {
    await readJson(layout.state.allowlist)
    return [{ name: 'allowlist.json', status: 'pass', detail: 'valid JSON' }]
  } catch {
    return [{ name: 'allowlist.json', status: 'fail', detail: 'malformed JSON',
      fixable: 'unfixable', fixNote: 'fix manually' }]
  }
}

// ─── orchestration ───────────────────────────────────────────────────────────

const ALL_CHECKS: { section: string; checks: CheckFn[] }[] = [
  { section: 'Structure',  checks: [checkStructure] },
  { section: 'Config',     checks: [checkBaseline, checkBootMd, checkPersona] },
  { section: 'Identity',   checks: [checkImprint] },
  { section: 'Integrity',  checks: [checkIntegrityDoc, checkIntegrityChain] },
  { section: 'Runtime',    checks: [checkSessionToken, checkSkillsIndex, checkAllowlist] },
]

async function runChecks(root: string, fix: boolean): Promise<{ section: string; results: CheckResult[] }[]> {
  const out: { section: string; results: CheckResult[] }[] = []
  for (const group of ALL_CHECKS) {
    const results: CheckResult[] = []
    for (const check of group.checks) {
      results.push(...await check(root, fix))
    }
    out.push({ section: group.section, results })
  }
  return out
}

function icon(c: CheckResult): string {
  if (c.fixable === 'fixed') return '⚡'
  if (c.status === 'pass') return '✓'
  if (c.status === 'warn') return '⚠'
  return '✗'
}

async function runDoctor(entityId: string | undefined, fix: boolean): Promise<void> {
  const root = await resolveEntityRoot(entityId)
  const groups = await runChecks(root, fix)
  const all    = groups.flatMap(g => g.results)
  const fails  = all.filter(c => c.status === 'fail' && c.fixable !== 'fixed').length
  const warns  = all.filter(c => c.status === 'warn' && c.fixable !== 'fixed').length
  const fixed  = all.filter(c => c.fixable === 'fixed').length

  const w = process.stdout.write.bind(process.stdout)
  const bar = '─'.repeat(60)

  w(`\n  fcp doctor — ${path.basename(root)}${fix ? '  (--fix)' : ''}\n  ${bar}\n`)

  for (const group of groups) {
    w(`\n  ── ${group.section} ${'─'.repeat(55 - group.section.length)}\n`)
    for (const c of group.results) {
      const suffix = c.fixable === 'fixed'                     ? `  → ${c.fixNote}`
                   : c.fixNote && c.fixable === 'unfixable'    ? `  (${c.fixNote})`
                   : c.fixNote && !fix                         ? `  (${c.fixNote})`
                   : ''
      // Multi-line detail: indent continuation lines.
      const detailLines = c.detail.split('\n')
      w(`  ${icon(c)} ${c.name.padEnd(22)} ${detailLines[0]}${suffix}\n`)
      for (let i = 1; i < detailLines.length; i++) {
        w(`    ${' '.repeat(22)} ${detailLines[i]}\n`)
      }
    }
  }

  w(`\n  ${bar}\n`)
  const parts: string[] = []
  if (fixed > 0) parts.push(`${fixed} fixed`)
  parts.push(`${fails} failure(s)`)
  parts.push(`${warns} warning(s)`)
  w(`  ${parts.join(', ')}\n\n`)

  if (fails > 0) process.exit(1)
}

export function registerDoctor(program: Command): void {
  program
    .command('doctor')
    .description('Validate entity health and integrity')
    .option('--fix', 'Auto-fix recoverable issues (integrity rehash, stale tokens, missing dirs/index)')
    .action(async function (this: Command, opts: { fix?: boolean }) {
      const entity = (this.optsWithGlobals() as { entity?: string }).entity
      await runDoctor(entity, opts.fix === true)
    })
}
