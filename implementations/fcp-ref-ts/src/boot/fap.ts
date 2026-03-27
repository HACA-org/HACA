// First Activation Protocol — 8-step cold-start sequence.
// Triggered when memory/imprint.json is absent (layout.memory.imprint does not exist).

import { randomUUID } from 'node:crypto'
import * as fs from 'node:fs/promises'
import * as path from 'node:path'
import { fileExists, ensureDir, readJson, writeJson, appendJsonl } from '../store/io.js'
import { parseBaseline, parseSkillManifest } from '../store/parse.js'
import { sha256Digest, getTrackedFiles, hashTrackedFiles } from './integrity.js'
import { FAPError } from '../types/boot.js'
import type { FAPOptions, FAPResult } from '../types/boot.js'
import type { SkillEntry } from '../types/formats/skills.js'

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

    // Scan skills/lib/ manifests → build skills index
    const entries: SkillEntry[] = []
    for (const ent of await safeReaddir(layout.skills.lib)) {
      if (!ent.isDirectory()) continue
      const mp = path.join(layout.skills.lib, ent.name, 'manifest.json')
      if (!await fileExists(mp)) continue
      const m = parseSkillManifest(await readJson(mp))
      entries.push({ name: m.name, desc: m.description, manifest: `lib/${ent.name}/manifest.json`, class: m.class })
    }
    await ensureDir(layout.skills.dir)
    await track(layout.skills.index, { version: '1.0', skills: entries, aliases: {} })
    log.info('fap:step1:ok', { skills: entries.length })

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
    const operatorBound = { operator_name: operatorName, operator_email: operatorEmail, operator_hash: operatorHash }
    log.info('fap:step4:ok', { operator_name: operatorName })

    // ── Step 5: Integrity Document ───────────────────────────────────────────
    io.write('FAP 5/8: integrity document generation')
    const tracked = await getTrackedFiles(layout)
    const files = await hashTrackedFiles(layout, tracked)
    await ensureDir(layout.state.dir)
    await track(layout.state.integrity, { version: '1.0', algorithm: 'sha256', last_checkpoint: null, files })
    log.info('fap:step5:ok', { tracked: tracked.length })

    // ── Step 6: Imprint Record ───────────────────────────────────────────────
    io.write('FAP 6/8: imprint record finalization')
    const structural_baseline = sha256Digest(await fs.readFile(layout.state.baseline))
    const integrity_document  = sha256Digest(await fs.readFile(layout.state.integrity))
    const skills_index        = sha256Digest(await fs.readFile(layout.skills.index))
    // Infer profile from topology: opaque topology implies HACA-Evolve.
    const haca_profile = baseline.cpe.topology === 'opaque' ? 'haca-evolve' : 'haca-core'
    const now = new Date().toISOString()
    const imprint = {
      version: '1.0' as const,
      activated_at: now,
      haca_arch_version: '1.0.0',
      haca_profile,
      operator_bound: operatorBound,
      structural_baseline,
      integrity_document,
      skills_index,
    }
    await ensureDir(layout.memory.dir)
    await track(layout.memory.imprint, imprint)
    log.info('fap:step6:ok')

    // ── Step 7: Genesis Omega ────────────────────────────────────────────────
    io.write('FAP 7/8: genesis omega')
    const imprint_hash = sha256Digest(await fs.readFile(layout.memory.imprint))
    const genesis = { seq: 0, ts: now, type: 'genesis' as const, imprint_hash, prev_hash: null }
    await appendJsonl(layout.state.integrityChain, genesis)
    created.push(layout.state.integrityChain)
    log.info('fap:step7:ok', { imprint_hash })

    // ── Step 8: First Session Token ──────────────────────────────────────────
    io.write('FAP 8/8: first session token')
    const sessionId = randomUUID()
    await ensureDir(layout.state.sentinels.dir)
    await track(layout.state.sentinels.sessionToken, { session_id: sessionId, issued_at: now })

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

async function safeReaddir(dirPath: string): Promise<import('node:fs').Dirent[]> {
  try {
    return await fs.readdir(dirPath, { withFileTypes: true })
  } catch {
    return []
  }
}
