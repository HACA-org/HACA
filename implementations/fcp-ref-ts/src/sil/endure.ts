// SIL Endure — evolution proposal commit protocol.
// Proposals are queued by fcp_evolution_proposal (exec tool) in state/pending-proposals.json.
// runEndureProtocol() processes approved ones during the sleep cycle.
import { fileExists, readJson, writeJson } from '../store/io.js'
import { refreshIntegrityDoc, currentFileHashes } from './integrity.js'
import { appendEndureCommit } from './chain.js'
import { sha256Digest } from '../boot/integrity.js'
import type { Layout }   from '../types/store.js'
import type { Logger }   from '../types/logger.js'
import type { EndureProposal } from '../types/sil.js'

interface ProposalsFile {
  readonly proposals: (EndureProposal & { approvedAt?: string })[]
}

export async function readPendingProposals(layout: Layout): Promise<EndureProposal[]> {
  if (!await fileExists(layout.state.pendingProposals)) return []
  try {
    const data = await readJson(layout.state.pendingProposals) as ProposalsFile
    return data.proposals ?? []
  } catch {
    return []
  }
}

export async function approveProposal(layout: Layout, id: string): Promise<boolean> {
  if (!await fileExists(layout.state.pendingProposals)) return false
  const file = await readJson(layout.state.pendingProposals) as ProposalsFile
  const proposals = file.proposals ?? []
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
  if (!await fileExists(layout.state.pendingProposals)) return

  const file = await readJson(layout.state.pendingProposals) as ProposalsFile
  const proposals  = file.proposals ?? []
  const approved   = proposals.filter(p => p.approvedAt)
  const unapproved = proposals.filter(p => !p.approvedAt)

  if (approved.length === 0) return
  logger.info('sil:endure_start', { count: approved.length })

  for (const proposal of approved) {
    const evolutionAuthDigest = sha256Digest(`${proposal.id}:${proposal.content}`)

    const integrityDocHash = await refreshIntegrityDoc(layout)
    const files = await currentFileHashes(layout)

    await appendEndureCommit(layout, { evolutionAuthDigest, files, integrityDocHash })
    logger.info('sil:endure_commit', { id: proposal.id })
  }

  // Persist only unapproved proposals
  if (unapproved.length > 0) {
    await writeJson(layout.state.pendingProposals, { proposals: unapproved })
  } else {
    const { deleteFile } = await import('../store/io.js')
    await deleteFile(layout.state.pendingProposals).catch(() => undefined)
  }

  logger.info('sil:endure_complete', { processed: approved.length })
}
