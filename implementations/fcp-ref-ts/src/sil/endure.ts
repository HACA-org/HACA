// SIL Endure — evolution proposal queue and commit protocol.
// Proposals queue in state/pending-closure.json; runEndureProtocol() processes
// approved ones during the sleep cycle.
import { randomUUID } from 'node:crypto'
import { fileExists, readJson, writeJson } from '../store/io.js'
import { sha256Digest } from '../boot/integrity.js'
import { refreshIntegrityDoc, currentFileHashes } from './integrity.js'
import { appendEndureCommit } from './chain.js'
import type { Layout }   from '../types/store.js'
import type { Logger }   from '../types/logger.js'
import type { EndureProposal } from '../types/sil.js'

interface ProposalsFile {
  readonly proposals: (EndureProposal & { approvedAt?: string })[]
}

// ─── Proposal queue ──────────────────────────────────────────────────────────

export async function readPendingProposals(layout: Layout): Promise<EndureProposal[]> {
  if (!await fileExists(layout.state.pendingClosure)) return []
  try {
    const data = await readJson(layout.state.pendingClosure) as ProposalsFile
    return data.proposals ?? []
  } catch {
    return []
  }
}

export async function queueProposal(layout: Layout, content: string): Promise<EndureProposal> {
  const proposal: EndureProposal = {
    id:       randomUUID(),
    content,
    digest:   sha256Digest(content),
    queuedAt: new Date().toISOString(),
  }

  const existing = await readPendingProposals(layout)
  await writeJson(layout.state.pendingClosure, { proposals: [...existing, proposal] })
  return proposal
}

export async function approveProposal(layout: Layout, id: string): Promise<boolean> {
  const file = await readJson(layout.state.pendingClosure) as ProposalsFile
  const proposals = file.proposals ?? []
  const idx = proposals.findIndex(p => p.id === id)
  if (idx < 0) return false

  const updated = proposals.map((p, i) =>
    i === idx ? { ...p, approvedAt: new Date().toISOString() } : p,
  )
  await writeJson(layout.state.pendingClosure, { proposals: updated })
  return true
}

// ─── Endure protocol ─────────────────────────────────────────────────────────

export async function runEndureProtocol(layout: Layout, logger: Logger): Promise<void> {
  if (!await fileExists(layout.state.pendingClosure)) return

  const file = await readJson(layout.state.pendingClosure) as ProposalsFile
  const proposals  = file.proposals ?? []
  const approved   = proposals.filter(p => p.approvedAt)
  const unapproved = proposals.filter(p => !p.approvedAt)

  if (approved.length === 0) return
  logger.info('sil:endure_start', { count: approved.length })

  for (const proposal of approved) {
    // Integrity digest = sha256Digest(content || id) — a stable per-proposal auth token
    const evolution_auth_digest = sha256Digest(`${proposal.id}:${proposal.content}`)

    // Update integrity doc and capture new file hashes
    const integrity_doc_hash = await refreshIntegrityDoc(layout)
    const files = await currentFileHashes(layout)

    await appendEndureCommit(layout, { evolution_auth_digest, files, integrity_doc_hash })
    logger.info('sil:endure_commit', { id: proposal.id })
  }

  // Persist only unapproved proposals
  if (unapproved.length > 0) {
    await writeJson(layout.state.pendingClosure, { proposals: unapproved })
  } else {
    // Remove the file if nothing remains
    const { deleteFile } = await import('../store/io.js')
    await deleteFile(layout.state.pendingClosure).catch(() => undefined)
  }

  logger.info('sil:endure_complete', { processed: approved.length })
}
