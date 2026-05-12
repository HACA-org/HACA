// Boot proposal gate — interactive review of pending evolution proposals.
// Called by phase6 when pending-proposals.json has unapproved entries.
// Uses the same sisteransi-based select UI as fcp init.
import { createInterface } from 'node:readline'
import chalk from 'chalk'
import { writeJson, deleteFile } from '../store/io.js'
import { appendIntegrityLog } from '../sil/integrity.js'
import { readPendingProposals } from '../sil/endure.js'
import { select, hr } from '../cli/ui/prompt.js'
import type { EndureProposal } from '../types/sil.js'
import type { Layout } from '../types/store.js'
import type { Logger } from '../types/logger.js'

function makeRl() {
  return createInterface({ input: process.stdin, output: process.stdout, terminal: true })
}

// Display a single proposal and prompt the operator to approve or reject.
// Returns true if approved, false if rejected.
async function reviewProposal(
  proposal: EndureProposal,
  index:    number,
  total:    number,
): Promise<boolean> {
  const rl = makeRl()
  try {
    process.stdout.write('\n')
    hr(`Proposal ${index + 1} of ${total}`)
    process.stdout.write(`  ${chalk.bold('ID:')}          ${chalk.dim(proposal.id)}\n`)
    process.stdout.write(`  ${chalk.bold('Description:')} ${proposal.description}\n`)
    process.stdout.write(`  ${chalk.bold('Ops:')}         ${proposal.ops.length} operation(s)\n`)
    for (const op of proposal.ops) {
      const location = 'path' in op
        ? ` ${chalk.dim((op as { path: string }).path)}`
        : 'name' in op
          ? ` ${chalk.dim((op as { name: string }).name)}`
          : ''
      process.stdout.write(`                ${chalk.dim('·')} ${op.type}${location}\n`)
    }
    process.stdout.write(`  ${chalk.bold('Queued:')}      ${chalk.dim(proposal.queuedAt)}\n`)
    process.stdout.write('\n')

    const res = await select(rl, 'Decision', [
      { label: 'Approve', description: 'execute this proposal in the next sleep cycle' },
      { label: 'Reject',  description: 'discard this proposal permanently' },
    ], 1)

    return res.index === 0
  } finally {
    try { process.stdin.setRawMode?.(false) } catch { /* ignore */ }
    process.stdout.write('\x1b[?25h')
    rl.close()
  }
}

// Review all unapproved proposals interactively.
// Persists approvals (sets approvedAt) and rejections (writes EVOLUTION_REJECTED
// to integrity.log and removes from queue). Throws BootError if the operator
// cancels mid-gate — the entity cannot boot with unreviewed proposals.
export async function runProposalGate(layout: Layout, logger: Logger): Promise<void> {
  const allProposals = await readPendingProposals(layout)
  const pending = allProposals.filter(p => !p.approvedAt)
  if (pending.length === 0) return

  process.stdout.write('\n')
  process.stdout.write(
    `  ${chalk.yellow('⚠')} ${chalk.bold(`${pending.length} evolution proposal(s) require your review before boot.`)}\n`,
  )
  process.stdout.write(
    `  ${chalk.dim('All proposals must be approved or rejected before the entity can start.')}\n`,
  )

  const ts = new Date().toISOString()
  // Work on a mutable copy so we can splice rejected entries out
  const queue: EndureProposal[] = [...allProposals]

  for (let i = 0; i < pending.length; i++) {
    const proposal = pending[i]!
    const approved = await reviewProposal(proposal, i, pending.length)

    if (approved) {
      const idx = queue.findIndex(p => p.id === proposal.id)
      if (idx >= 0) queue[idx] = { ...queue[idx]!, approvedAt: ts }
      process.stdout.write(`  ${chalk.green('✓')} Approved.\n`)
      logger.info('boot:proposal_gate:approved', { id: proposal.id })
    } else {
      const idx = queue.findIndex(p => p.id === proposal.id)
      if (idx >= 0) queue.splice(idx, 1)
      await appendIntegrityLog(layout, {
        event:  'EVOLUTION_REJECTED',
        id:     proposal.id,
        digest: proposal.digest,
        ts,
        reason: 'operator_declined_at_boot',
      })
      process.stdout.write(`  ${chalk.red('✗')} Rejected.\n`)
      logger.info('boot:proposal_gate:rejected', { id: proposal.id })
    }
  }

  // Persist updated queue or remove file if all entries were processed
  if (queue.length > 0) {
    await writeJson(layout.state.pendingProposals, { proposals: queue })
  } else {
    await deleteFile(layout.state.pendingProposals).catch(() => undefined)
  }

  process.stdout.write('\n')
  hr()
  process.stdout.write('\n')
}
