// First Activation Protocol — 8-step cold-start sequence.
// Triggered when memory/imprint.json is absent (layout.memory.imprint does not exist).

import { randomUUID } from 'node:crypto'
import * as fs from 'node:fs/promises'
import * as path from 'node:path'
import { createRequire } from 'node:module'
import { fileExists, ensureDir, readJson, writeJson, appendJsonl } from '../store/io.js'
import { parseBaseline } from '../store/parse.js'
import { sha256Digest, getTrackedFiles, hashTrackedFiles } from './integrity.js'
import { FAPError } from '../types/boot.js'
import type { FAPOptions, FAPResult } from '../types/boot.js'

const require = createRequire(import.meta.url)
const { version: fcpVersion } = require('../../package.json') as { version: string }

export async function runFAP(opts: FAPOptions): Promise<FAPResult> {
  const { layout, operatorName, operatorEmail, logger, io } = opts
  const log = logger.child({ phase: 'FAP' })

  // Track created files for rollback on failure.
  const created: string[] = []
  async function track(filePath: string, data: unknown): Promise<void> {
    await writeJson(filePath, data)
    created.push(filePath)
  }

  try {
    // ── Step 1: Structural Validation ──────────────────────────────────────
    io.write('FAP 1/8: structural validation')
    if (!await fileExists(layout.bootMd)) throw new FAPError(1, 'boot.md not found')
    if (!await fileExists(layout.state.baseline)) throw new FAPError(1, 'state/baseline.json not found')

    const baselineRaw = await readJson(layout.state.baseline)
    const baseline = parseBaseline(baselineRaw)

    // Built-in tools live in exec/tools/ — skills/ contains only operator/entity custom skills.
    // At FAP time there are no custom skills yet; the index starts empty.
    await ensureDir(layout.skills.dir)
    await track(layout.skills.index, { version: '1.0', skills: [], aliases: {} })

    // Pre-populate allowlist with safe read-only commands.
    // Excludes: cat (duplicates fcp_file_read), git (potentially destructive),
    // rm/mv/cp/mkdir/touch (conflict with fcp_file_write).
    await ensureDir(layout.state.dir)
    await track(layout.state.allowlist, {
      commands: [
        'ls', 'find', 'wc', 'grep', 'head', 'tail', 'echo', 'pwd', 'date',
        'env', 'printenv', 'uname', 'which', 'stat', 'file', 'diff', 'sort',
        'uniq', 'tr', 'cut', 'awk', 'sed', 'jq',
      ],
      domains: [],
      skills:  [],
    })
    log.info('fap:step1:ok', { skills: 0 })

    // ── Step 2: Host Environment Capture ───────────────────────────────────
    io.write('FAP 2/8: host environment capture')
    if (baseline.cpe.topology !== 'transparent') {
      io.write(`  topology: ${baseline.cpe.topology}`)
    }
    log.info('fap:step2:ok', { topology: baseline.cpe.topology })

    // ── Step 3: Operator Channel Initialization ─────────────────────────────
    io.write('FAP 3/8: operator channel initialization')
    await ensureDir(layout.state.operatorNotifications)
    log.info('fap:step3:ok')

    // ── Step 4: Operator Enrollment ─────────────────────────────────────────
    io.write('FAP 4/8: operator enrollment')
    const operatorHash = sha256Digest(`${operatorName}\n${operatorEmail}`)
    const operatorBound = { operatorName, operatorEmail, operatorHash }
    log.info('fap:step4:ok', { operatorName })

    // ── Step 5: Integrity Document ───────────────────────────────────────────
    io.write('FAP 5/8: integrity document generation')
    const tracked = await getTrackedFiles(layout)
    const files = await hashTrackedFiles(layout, tracked)
    await ensureDir(layout.state.dir)
    await track(layout.state.integrity, { version: '1.0', algorithm: 'sha256', lastCheckpoint: null, files })
    log.info('fap:step5:ok', { tracked: tracked.length })

    // ── Step 6: Imprint Record ───────────────────────────────────────────────
    io.write('FAP 6/8: imprint record finalization')
    const structuralBaseline = sha256Digest(await fs.readFile(layout.state.baseline))
    const integrityDocument  = sha256Digest(await fs.readFile(layout.state.integrity))
    const skillsIndex        = sha256Digest(await fs.readFile(layout.skills.index))
    // Infer profile from topology: opaque topology implies HACA-Evolve.
    const hacaProfile = baseline.cpe.topology === 'opaque' ? 'HACA-Evolve-1.0.0' : 'HACA-Core-1.0.0'
    const now = new Date().toISOString()
    const imprint = {
      version: '1.0' as const,
      activatedAt: now,
      fcpVersion,
      hacaArchVersion: '1.0.0',
      hacaProfile,
      operatorBound,
      structuralBaseline,
      integrityDocument,
      skillsIndex,
    }
    await ensureDir(layout.memory.dir)
    await track(layout.memory.imprint, imprint)
    log.info('fap:step6:ok')

    // ── Step 7: Genesis Omega ────────────────────────────────────────────────
    io.write('FAP 7/8: genesis omega')
    const imprintHash = sha256Digest(await fs.readFile(layout.memory.imprint))
    const genesis = { seq: 0, ts: now, type: 'genesis' as const, imprintHash, prevHash: null }
    await appendJsonl(layout.state.integrityChain, genesis)
    created.push(layout.state.integrityChain)
    log.info('fap:step7:ok', { imprintHash })

    // ── Step 8: First Session Token ──────────────────────────────────────────
    io.write('FAP 8/8: first session token')
    const sessionId = randomUUID()
    await ensureDir(layout.state.sentinels.dir)
    await track(layout.state.sentinels.sessionToken, { sessionId, issuedAt: now })

    log.info('fap:complete', { sessionId })
    io.write('FAP complete.')
    return { ok: true, sessionId }

  } catch (err: unknown) {
    log.error('fap:failed — rolling back', { err: String(err) })
    for (const f of [...created].reverse()) {
      await fs.unlink(f).catch(() => undefined)
    }
    if (err instanceof FAPError) return { ok: false, step: err.step, reason: err.message }
    return { ok: false, step: 0, reason: String(err) }
  }
}

