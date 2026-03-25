import { existsSync } from 'node:fs'
import { cp, rm, readdir } from 'node:fs/promises'
import { join } from 'node:path'
import type { Layout } from '../store/layout.js'
import { readJson, writeJson } from '../store/io.js'
import type { Logger } from '../logger/logger.js'
import { auditSkillPath } from '../exec/tools/skillAudit.js'
import { writeIntegrityDoc, sha256Str } from './integrity.js'
import { logEndureCommit } from './chain.js'
import type { PendingProposal } from './types.js'

// ---------------------------------------------------------------------------
// Pending proposals
// ---------------------------------------------------------------------------

interface ProposalsFile {
  proposals: PendingProposal[]
}

export async function readPendingProposals(layout: Layout): Promise<PendingProposal[]> {
  if (!existsSync(layout.pendingClosure)) return []
  try {
    const data = await readJson<ProposalsFile>(layout.pendingClosure)
    return data.proposals ?? []
  } catch {
    return []
  }
}

export async function writePendingProposals(layout: Layout, proposals: PendingProposal[]): Promise<void> {
  if (proposals.length === 0 && existsSync(layout.pendingClosure)) {
    const { removeFile } = await import('../store/io.js')
    await removeFile(layout.pendingClosure)
    return
  }
  if (proposals.length > 0) {
    await writeJson(layout.pendingClosure, { proposals })
  }
}

// ---------------------------------------------------------------------------
// Skill installation
// ---------------------------------------------------------------------------

async function installSkill(
  layout: Layout,
  proposal: PendingProposal,
  logger: Logger,
): Promise<{ ok: boolean; reason?: string }> {
  const stagePath = proposal.stagePath
  if (!stagePath) return { ok: false, reason: 'no stagePath in proposal' }
  if (!existsSync(stagePath)) return { ok: false, reason: `stage not found: ${stagePath}` }

  // Audit before installing
  const audit = await auditSkillPath(stagePath)
  if (audit.verdict !== 'PASS') {
    const reasons = audit.findings.map(f => `[${f.severity}] ${f.location}: ${f.message}`)
    return { ok: false, reason: `skillAudit FAIL: ${reasons.join('; ')}` }
  }

  // Read manifest to get skill name
  const manifest = await readJson<{ name: string }>(join(stagePath, 'manifest.json'))
  const skillName = manifest.name
  const destPath = layout.skill(skillName)

  // Copy stage to skills/
  await cp(stagePath, destPath, { recursive: true })
  await logger.info('sil', 'skill_installed', { skill: skillName, from: stagePath, to: destPath })

  // Update skills/index.json
  await _updateSkillIndex(layout, skillName)

  // Clean up stage
  await rm(stagePath, { recursive: true, force: true })
  await logger.info('sil', 'stage_cleaned', { stagePath })

  return { ok: true }
}

async function _updateSkillIndex(layout: Layout, newSkillName: string): Promise<void> {
  let index: { version: string; skills: Array<{ name: string; manifest: string }> } = {
    version: '1.0',
    skills: [],
  }

  if (existsSync(layout.skillsIndex)) {
    try {
      index = await readJson(layout.skillsIndex)
    } catch {
      // start fresh
    }
  }

  const manifestRel = `skills/${newSkillName}/manifest.json`
  const existing = index.skills.findIndex(s => s.name === newSkillName)
  const entry = { name: newSkillName, manifest: manifestRel }

  if (existing >= 0) {
    index.skills[existing] = entry
  } else {
    index.skills.push(entry)
  }

  await writeJson(layout.skillsIndex, index)
}

// ---------------------------------------------------------------------------
// Endure protocol — called from sleep cycle
// ---------------------------------------------------------------------------

/**
 * Process pending approved proposals during sleep cycle.
 * Handles skill installation, updates integrity.json, appends ENDURE_COMMIT to chain.
 * TODO: scope audit for haca-evolve — validate proposals against authorized scope
 */
export async function runEndureProtocol(
  layout: Layout,
  logger: Logger,
  profile: 'haca-core' | 'haca-evolve',
): Promise<void> {
  await logger.info('sil', 'endure_start', { profile })

  const proposals = await readPendingProposals(layout)
  const approved = proposals.filter(p => p.approvedAt)

  if (approved.length === 0) {
    await logger.info('sil', 'endure_no_proposals')
    return
  }

  const remaining: PendingProposal[] = proposals.filter(p => !p.approvedAt)

  for (const proposal of approved) {
    await logger.info('sil', 'endure_processing', { operation: proposal.operation, id: proposal.id })

    if (proposal.operation === 'installSkill') {
      const result = await installSkill(layout, proposal, logger)
      if (!result.ok) {
        await logger.error('sil', 'endure_skill_install_failed', { id: proposal.id, reason: result.reason })
        // Keep proposal as pending (not approved) for retry
        remaining.push({ ...proposal, approvedAt: undefined })
        continue
      }
    }

    // Update integrity.json after each successful operation
    await writeIntegrityDoc(layout)

    // Compute evolution auth digest from proposal
    const evolutionAuthDigest = sha256Str(JSON.stringify(proposal))

    // Append ENDURE_COMMIT to chain
    await logEndureCommit(layout, proposal.operation, proposal.id, evolutionAuthDigest)
    await logger.info('sil', 'endure_commit', { operation: proposal.operation, id: proposal.id })
  }

  // Persist remaining (unapproved) proposals
  await writePendingProposals(layout, remaining)
  await logger.info('sil', 'endure_complete', { processed: approved.length, remaining: remaining.length })
}
