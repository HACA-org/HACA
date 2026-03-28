// SIL Endure — structural evolution commit protocol.
// Runs during the sleep cycle (Stage 3). Processes proposals with approvedAt set.
//
// Pipeline per proposal:
//   1. Snapshot entity root → state/snapshots/<id>/
//   2. Execute ops atomically (fileWrite via atomicWrite, fileDelete, jsonMerge, skillInstall)
//   3. Refresh integrity.json
//   4. Append ENDURE_COMMIT to integrity-chain.jsonl
//   5. Remove snapshot on success
//   6. Write EVOLUTION_AUTH to integrity.log (if not already written — HACA-Core path)
//
// After all proposals: write SLEEP_COMPLETE to integrity.log, remove pending file.
import * as path from 'node:path'
import * as fs from 'node:fs/promises'
import { z } from 'zod'
import { fileExists, readJson, writeJson, deleteFile, ensureDir, atomicWrite } from '../store/io.js'
import { refreshIntegrityDoc, currentFileHashes, appendIntegrityLog } from './integrity.js'
import { appendEndureCommit } from './chain.js'
import { sha256Digest } from '../boot/integrity.js'
import { auditSkillDir } from '../exec/tools/skill-audit.js'
import { EvolutionOpSchema } from '../types/formats/evolution.js'
import type { EvolutionOp } from '../types/formats/evolution.js'
import type { Layout }   from '../types/store.js'
import type { Logger }   from '../types/logger.js'
import type { EndureProposal } from '../types/sil.js'

// ─── proposals file schema ────────────────────────────────────────────────────

const ProposalSchema = z.object({
  id:          z.string(),
  description: z.string(),
  ops:         z.array(EvolutionOpSchema),
  digest:      z.string(),
  queuedAt:    z.string(),
  approvedAt:  z.string().optional(),
})

const ProposalsFileSchema = z.object({
  proposals: z.array(ProposalSchema),
})

async function loadProposalsFile(layout: Layout): Promise<EndureProposal[]> {
  if (!await fileExists(layout.state.pendingProposals)) return []
  try {
    const raw = await readJson(layout.state.pendingProposals)
    return ProposalsFileSchema.parse(raw).proposals as EndureProposal[]
  } catch {
    return []
  }
}

export async function readPendingProposals(layout: Layout): Promise<EndureProposal[]> {
  return loadProposalsFile(layout)
}

export async function approveProposal(layout: Layout, id: string): Promise<boolean> {
  const proposals = await loadProposalsFile(layout)
  const idx = proposals.findIndex(p => p.id === id)
  if (idx < 0) return false

  const updated = proposals.map((p, i) =>
    i === idx ? { ...p, approvedAt: new Date().toISOString() } : p,
  )
  await writeJson(layout.state.pendingProposals, { proposals: updated })
  return true
}

// ─── op execution ─────────────────────────────────────────────────────────────

async function executeOp(op: EvolutionOp, root: string, workspaceFocus: string, logger: Logger): Promise<void> {
  switch (op.type) {
    case 'fileWrite': {
      const abs = path.join(root, op.path)
      await ensureDir(path.dirname(abs))
      await atomicWrite(abs, op.content)
      break
    }

    case 'fileDelete': {
      const abs = path.join(root, op.path)
      await fs.unlink(abs).catch((e: NodeJS.ErrnoException) => {
        if (e.code !== 'ENOENT') throw e
      })
      break
    }

    case 'jsonMerge': {
      const abs = path.join(root, op.path)
      let existing: Record<string, unknown> = {}
      if (await fileExists(abs)) {
        try { existing = await readJson(abs) as Record<string, unknown> } catch { /* start empty */ }
      }
      const merged = Object.assign({}, existing, op.patch)
      await ensureDir(path.dirname(abs))
      await atomicWrite(abs, JSON.stringify(merged, null, 2))
      break
    }

    case 'skillInstall': {
      // Validate the staged skill before installing
      const stageDir = path.join(workspaceFocus, 'tmp', 'fcp-stage', op.name)
      const audit    = await auditSkillDir(stageDir, logger, op.name)
      if (!audit.ok) throw new Error(`skillInstall audit failed: ${audit.error}`)
      if (audit.report.issues.length > 0) {
        throw new Error(`skillInstall audit issues: ${audit.report.issues.join('; ')}`)
      }

      // Copy staged skill to skills/<name>/
      const destDir = path.join(root, 'skills', op.name)
      await fs.rm(destDir, { recursive: true, force: true })
      await fs.cp(stageDir, destDir, { recursive: true })

      // Register in skills/index.json
      const indexPath = path.join(root, 'skills', 'index.json')
      let index: { version: string; skills: unknown[]; aliases: Record<string, unknown> } =
        { version: '1.0', skills: [], aliases: {} }
      if (await fileExists(indexPath)) {
        try { index = await readJson(indexPath) as typeof index } catch { /* start fresh */ }
      }
      const existing = (index.skills as Array<{ name: string }>).filter(s => s.name !== op.name)
      index.skills = [...existing, {
        name:     op.name,
        desc:     audit.report.description,
        manifest: path.join(op.name, 'manifest.json'),
        class:    audit.report.class,
      }]
      await atomicWrite(indexPath, JSON.stringify(index, null, 2))

      // Clean up staging directory
      await fs.rm(stageDir, { recursive: true, force: true })

      logger.info('sil:endure:skill_installed', { name: op.name })
      break
    }
  }
}

// ─── snapshot helpers ─────────────────────────────────────────────────────────

async function snapshotProposal(layout: Layout, proposalId: string): Promise<string> {
  const snapshotDir = path.join(layout.state.snapshots, proposalId)
  await ensureDir(snapshotDir)
  // Write proposal ID as a sentinel file — full file-level snapshots are
  // optional in the reference implementation; the chain entry is the durable record.
  await atomicWrite(path.join(snapshotDir, 'proposal.id'), proposalId)
  return snapshotDir
}

async function removeSnapshot(snapshotDir: string): Promise<void> {
  await fs.rm(snapshotDir, { recursive: true, force: true }).catch(() => undefined)
}

// ─── Endure Protocol ──────────────────────────────────────────────────────────

export async function runEndureProtocol(layout: Layout, logger: Logger): Promise<void> {
  const proposals  = await loadProposalsFile(layout)
  const approved   = proposals.filter(p => p.approvedAt)
  const unapproved = proposals.filter(p => !p.approvedAt)
  const ts         = new Date().toISOString()

  if (approved.length === 0) {
    await appendIntegrityLog(layout, { event: 'SLEEP_COMPLETE', ts, proposed: proposals.length, executed: 0 })
    return
  }

  // Read workspace_focus for skillInstall ops — fail fast if missing when needed
  let workspaceFocus = ''
  try {
    const raw = await readJson(layout.state.workspaceFocus) as Record<string, unknown>
    workspaceFocus = typeof raw['path'] === 'string' ? raw['path'].trim() : ''
  } catch { /* not set — skillInstall ops will fail if workspace is missing */ }

  logger.info('sil:endure_start', { count: approved.length })

  let executed = 0
  for (const proposal of approved) {
    logger.info('sil:endure:proposal_start', { id: proposal.id })

    // 1. Snapshot
    const snapshotDir = await snapshotProposal(layout, proposal.id)

    try {
      // 2. Execute ops
      for (const op of proposal.ops) {
        await executeOp(op, layout.root, workspaceFocus, logger)
      }

      // 3. Refresh integrity.json
      const integrityDocHash = await refreshIntegrityDoc(layout)

      // 4. Append ENDURE_COMMIT to chain
      const evolutionAuthDigest = sha256Digest(`${proposal.id}:${proposal.digest}`) as `sha256:${string}`
      const files               = await currentFileHashes(layout)
      await appendEndureCommit(layout, { evolutionAuthDigest, files, integrityDocHash })

      // 5. Remove snapshot
      await removeSnapshot(snapshotDir)

      // 6. Write EVOLUTION_AUTH (HACA-Core path — HACA-Evolve writes it at queue time)
      // Only write if approvedAt != queuedAt (i.e., manually approved, not auto-approved).
      if (proposal.approvedAt !== proposal.queuedAt) {
        await appendIntegrityLog(layout, {
          event: 'EVOLUTION_AUTH', id: proposal.id, digest: proposal.digest,
          ts: proposal.approvedAt!, autoApproved: false,
        })
      }

      executed++
      logger.info('sil:endure_commit', { id: proposal.id })
    } catch (e: unknown) {
      logger.error('sil:endure:proposal_failed', { id: proposal.id, err: String(e) })
      await appendIntegrityLog(layout, {
        event: 'EVOLUTION_REJECTED', id: proposal.id, digest: proposal.digest,
        ts: new Date().toISOString(), reason: String(e),
      })
      // Continue with remaining proposals — one failure must not block others.
    }
  }

  // Persist only unapproved proposals; remove file if all processed
  if (unapproved.length > 0) {
    await writeJson(layout.state.pendingProposals, { proposals: unapproved })
  } else {
    await deleteFile(layout.state.pendingProposals).catch(() => undefined)
  }

  await appendIntegrityLog(layout, {
    event: 'SLEEP_COMPLETE', ts: new Date().toISOString(),
    proposed: approved.length, executed,
  })

  logger.info('sil:endure_complete', { processed: executed, failed: approved.length - executed })
}
