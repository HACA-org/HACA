// SIL Endure — evolution proposal commit protocol.
// Proposals are queued by fcp_evolution_proposal in state/pending-proposals.json.
// runEndureProtocol() processes approved ones during the sleep cycle.
import { z } from 'zod'
import { fileExists, readJson, writeJson, deleteFile } from '../store/io.js'
import { refreshIntegrityDoc, currentFileHashes } from './integrity.js'
import { appendEndureCommit } from './chain.js'
import { sha256Digest } from '../boot/integrity.js'
import type { Layout }   from '../types/store.js'
import type { Logger }   from '../types/logger.js'
import type { EndureProposal } from '../types/sil.js'

const ProposalSchema = z.object({
  id:         z.string(),
  content:    z.string(),
  digest:     z.string(),
  queuedAt:   z.string(),
  approvedAt: z.string().optional(),
})

const ProposalsFileSchema = z.object({
  proposals: z.array(ProposalSchema),
})

type Proposal = z.infer<typeof ProposalSchema>

async function loadProposalsFile(layout: Layout): Promise<Proposal[]> {
  if (!await fileExists(layout.state.pendingProposals)) return []
  try {
    const raw = await readJson(layout.state.pendingProposals)
    return ProposalsFileSchema.parse(raw).proposals
  } catch {
    return []
  }
}

export async function readPendingProposals(layout: Layout): Promise<EndureProposal[]> {
  return loadProposalsFile(layout) as Promise<EndureProposal[]>
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

// ─── Endure protocol ─────────────────────────────────────────────────────────

export async function runEndureProtocol(layout: Layout, logger: Logger): Promise<void> {
  const proposals  = await loadProposalsFile(layout)
  const approved   = proposals.filter(p => p.approvedAt)
  const unapproved = proposals.filter(p => !p.approvedAt)

  if (approved.length === 0) return
  logger.info('sil:endure_start', { count: approved.length })

  for (const proposal of approved) {
    const evolutionAuthDigest = sha256Digest(`${proposal.id}:${proposal.content}`)
    const integrityDocHash    = await refreshIntegrityDoc(layout)
    const files               = await currentFileHashes(layout)
    await appendEndureCommit(layout, { evolutionAuthDigest, files, integrityDocHash })
    logger.info('sil:endure_commit', { id: proposal.id })
  }

  // Persist only unapproved proposals; remove file if all approved
  if (unapproved.length > 0) {
    await writeJson(layout.state.pendingProposals, { proposals: unapproved })
  } else {
    await deleteFile(layout.state.pendingProposals).catch(() => undefined)
  }

  logger.info('sil:endure_complete', { processed: approved.length })
}
