// /endure slash command — evolution proposal management (list, approve, reject, sync).
import chalk from 'chalk'
import { readPendingProposals, approveProposal } from '../sil/endure.js'
import { appendIntegrityLog } from '../sil/integrity.js'
import type { SlashCommand, SlashResult } from './slash.js'
import type { AppState } from '../types/tui.js'

async function execute(args: string, state: AppState): Promise<SlashResult> {
  const [sub, id] = args.trim().split(/\s+/)
  const subCmd = (sub ?? 'list').toLowerCase()

  // /endure sync — deferred, not yet implemented
  if (subCmd === 'sync') {
    return {
      action: 'display',
      lines:  [chalk.dim('  /endure sync — not yet implemented (future: git remote sync)')],
    }
  }

  // Load proposals from disk
  let proposals: Awaited<ReturnType<typeof readPendingProposals>>
  try {
    proposals = await readPendingProposals(state.layout)
  } catch {
    return { action: 'display', lines: [chalk.red('  Error reading proposals')] }
  }

  // /endure list
  if (subCmd === 'list') {
    if (proposals.length === 0) {
      return { action: 'display', lines: [chalk.dim('  No evolution proposals in queue.')] }
    }
    const lines = proposals.map(p => {
      const status = p.approvedAt
        ? chalk.green('approved')
        : chalk.yellow('pending')
      return `  ${chalk.dim(p.id.slice(0, 8))}  ${status}  ${p.description}`
    })
    lines.unshift(chalk.bold(`  ${proposals.length} proposal(s):`))
    return { action: 'display', lines }
  }

  // /endure approve <id> and /endure reject <id> require an id
  if (subCmd === 'approve' || subCmd === 'reject') {
    if (!id) {
      return {
        action: 'display',
        lines:  [`  Usage: ${chalk.cyan(`/endure ${subCmd} <id>`)}`],
      }
    }

    const prefix = id.toLowerCase()
    const match = proposals.find(p =>
      p.id === prefix || p.id.startsWith(prefix),
    )
    if (!match) {
      return { action: 'display', lines: [chalk.red(`  No proposal found matching: ${id}`)] }
    }
    if (match.approvedAt) {
      return {
        action: 'display',
        lines:  [chalk.dim(`  Proposal ${match.id.slice(0, 8)} is already approved.`)],
      }
    }

    if (subCmd === 'approve') {
      await approveProposal(state.layout, match.id)
      return {
        action: 'inject',
        text:   'SYSTEM: Operator approved an evolution proposal. Call fcp_closure_payload to save state, then call fcp_session_close with reboot: true so the sleep cycle can execute the approved proposal.',
      }
    } else {
      await appendIntegrityLog(state.layout, {
        event:  'EVOLUTION_REJECTED',
        id:     match.id,
        digest: match.digest,
        ts:     new Date().toISOString(),
        reason: 'operator_declined_mid_session',
      })
      return {
        action: 'display',
        lines:  [chalk.dim(`  Proposal ${match.id.slice(0, 8)} rejected.`)],
      }
    }
  }

  // Unknown sub-command
  return {
    action: 'display',
    lines: [
      `  Usage: ${chalk.cyan('/endure list')}`,
      `         ${chalk.cyan('/endure approve <id>')}`,
      `         ${chalk.cyan('/endure reject <id>')}`,
      `         ${chalk.dim('/endure sync  (not yet implemented)')}`,
    ],
  }
}

export const endureCmd: SlashCommand = {
  name:        '/endure',
  aliases:     [],
  description: 'Manage evolution proposals (list, approve <id>, reject <id>)',
  execute,
}
