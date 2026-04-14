// fcp run — boot entity, run session loop, run sleep cycle.
// Wires: startEntity → runSessionLoop → runSleepCycle.
// TTY: full TUI with scroll region + fixed bar. Non-TTY: plain line I/O.
import * as path from 'node:path'
import { createRequire } from 'node:module'
import { createInterface } from 'node:readline'
import type { Command } from 'commander'
import { createLayout } from '../../types/store.js'
import { createLogger }  from '../../logger/logger.js'
import { parseBaseline } from '../../store/parse.js'
import { readJson, fileExists } from '../../store/io.js'
import { startEntity }   from '../../boot/boot.js'
import { resolveAdapter } from '../../cpe/cpe.js'
import { loadAllowlistPolicy, fileReadHandler, fileWriteHandler, webFetchHandler,
         shellRunHandler, agentRunHandler, skillCreateHandler, skillAuditHandler } from '../../exec/exec.js'
import { memoryRecallHandler, memoryWriteHandler,
         closurePayloadHandler } from '../../mil/mil.js'
import { evolutionProposalHandler, sessionCloseHandler,
         readPendingProposals, approveProposal, appendIntegrityLog } from '../../sil/sil.js'
import { runSessionLoop }    from '../../session/loop.js'
import { runSleepCycle }     from '../../session/sleep.js'
import type { SessionIO, SessionEvent } from '../../types/session.js'
import { CLIError } from '../../types/cli.js'
import { resolveEntityRoot } from '../entity.js'
import { createTUI } from '../../tui/tui.js'
import { loadEntityStats, renderHeader, renderHeaderPlain } from '../../tui/header.js'

const require = createRequire(import.meta.url)
const { version: fcpVersion } = require('../../../package.json') as { version: string }

// ─── Non-TTY fallback IO ──────────────────────────────────────────────────────

function makeSharedRL() {
  const rl = createInterface({ input: process.stdin, output: process.stdout, terminal: false })
  const lineQueue: string[] = []
  const resolvers: Array<(s: string) => void> = []

  rl.on('line', (line: string) => {
    if (resolvers.length > 0) {
      resolvers.shift()!(line)
    } else {
      lineQueue.push(line)
    }
  })

  function nextLine(): Promise<string> {
    return new Promise(resolve => {
      if (lineQueue.length > 0) {
        resolve(lineQueue.shift()!)
      } else {
        resolvers.push(resolve)
      }
    })
  }

  return { rl, nextLine }
}

function makeConsoleIO(nextLine: () => Promise<string>): SessionIO {
  return {
    prompt(): Promise<string> {
      process.stdout.write('\n> ')
      return nextLine()
    },

    write(text: string): void {
      process.stdout.write(text + '\n')
    },

    emit(event: SessionEvent): void {
      if (event.type === 'cpe_response' && event.content) {
        process.stdout.write('\nAssistant: ' + event.content + '\n')
      } else if (event.type === 'tool_dispatch') {
        process.stdout.write(`[tool] ${event.skillName}\n`)
      } else if (event.type === 'session_close') {
        process.stdout.write(`[closed: ${event.reason}]\n`)
      }
    },
  }
}

// ─── Main ─────────────────────────────────────────────────────────────────────

async function runFcp(opts: { entity?: string; verbose?: boolean }): Promise<void> {
  const verbose    = opts.verbose === true
  const entityRoot = await resolveEntityRoot(opts.entity)
  const layout     = createLayout(entityRoot)
  const logger     = createLogger(verbose ? {} : { test: false }, { silent: !verbose })

  // Load and validate baseline
  if (!await fileExists(layout.state.baseline)) {
    throw new CLIError(`baseline.json not found at ${layout.state.baseline}. Run \`fcp init\`.`, 1)
  }
  const baselineRaw = await readJson(layout.state.baseline)
  const baseline    = parseBaseline(baselineRaw)

  const useTUI = process.stdout.isTTY === true

  // Non-TTY: shared readline for the entire lifecycle
  const shared = useTUI ? null : makeSharedRL()
  const nextLine = shared?.nextLine ?? (() => Promise.resolve(''))

  try {
    // ── Boot ──────────────────────────────────────────────────────────────────
    // In normal mode, suppress step-by-step FAP output; only show prompts.
    // In verbose mode, show all FAP detail.
    let isColdStart = false
    const bootIO = useTUI
      ? { write: (msg: string) => {
            if (msg.startsWith('FAP')) isColdStart = true
            if (verbose) process.stdout.write(msg + '\n')
          },
          prompt: (q: string) => new Promise<string>(resolve => {
            const rl = createInterface({ input: process.stdin, output: process.stdout, terminal: true })
            rl.question(q, (answer) => { rl.close(); resolve(answer) })
          }) }
      : { write: (msg: string) => {
            if (msg.startsWith('FAP')) isColdStart = true
            if (verbose) process.stdout.write(msg + '\n')
          },
          prompt: async (question: string) => {
            process.stdout.write(question)
            return (await nextLine()).trim()
          } }

    const bootResult = await startEntity({ layout, logger, io: bootIO, sleepCycle: runSleepCycle })

    if (!bootResult.ok) {
      throw new CLIError(`Boot failed (phase ${bootResult.phase}): ${bootResult.reason}`, 1)
    }

    const { sessionId, contextMessages } = bootResult
    const cpe    = resolveAdapter(baseline.cpe.backend)
    const policy = await loadAllowlistPolicy(layout)
    const tools  = [
      fileReadHandler, fileWriteHandler, webFetchHandler,
      shellRunHandler, agentRunHandler, skillCreateHandler, skillAuditHandler,
      memoryRecallHandler, memoryWriteHandler, closurePayloadHandler,
      evolutionProposalHandler, sessionCloseHandler,
    ]
    const profile = baseline.cpe.topology === 'opaque' ? 'HACA-Evolve' : 'HACA-Core'

    // ── Header ────────────────────────────────────────────────────────────────
    const cols  = process.stdout.columns || 80
    const stats = await loadEntityStats(layout, fcpVersion)
    const hdrLines = renderHeader(stats, cols)
    if (isColdStart && !verbose) {
      hdrLines.push('  ✓ First Activation Protocol complete')
    }

    // ── IO: TUI or console ────────────────────────────────────────────────────
    // TUI is created once and reused across reboots — operator sees continuous chat.
    let io: SessionIO
    let tui: (SessionIO & { teardown(): void; clearChat(): void }) | null = null

    if (useTUI) {
      const t = createTUI({
        sessionId,
        profile,
        contextWindow: cpe.contextWindow,
        provider:      cpe.provider,
        model:         cpe.model,
        fcpVersion:    fcpVersion,
        headerLines:   hdrLines,
        verbose,
      })
      tui = t
      io  = t
    } else {
      // Non-TTY: render plain header once
      const plainLines = renderHeaderPlain(stats, cols)
      if (isColdStart && !verbose) {
        plainLines.push('  ✓ First Activation Protocol complete')
      }
      for (const line of plainLines) process.stdout.write(line + '\n')
      process.stdout.write('\n')
      io = makeConsoleIO(nextLine)
    }

    // ── Session + reboot loop ─────────────────────────────────────────────────
    // Runs session → sleep cycle → (optionally) boot → session again.
    // Any component (slash command, endure, skill) can trigger a reboot by
    // returning closed: 'reboot' from runSessionLoop.
    let currentSessionId    = sessionId
    let currentContextMsgs  = contextMessages

    try {
      while (true) {
        const result = await runSessionLoop({
          layout, baseline, cpe, policy, tools, logger,
          io,
          sessionId:      currentSessionId,
          profile,
          contextWindow:  cpe.contextWindow,
          ...(currentContextMsgs ? { contextMessages: currentContextMsgs } : {}),
        })

        // ── HACA-Core: present pending proposals for Operator approval ────────
        if (!baseline.authorizationScope) {
          const pending = await readPendingProposals(layout)
          if (pending.length > 0) {
            io.write(`── Evolution Proposals (${pending.length}) ──`)
            for (const proposal of pending) {
              if (proposal.approvedAt) continue
              io.write(`Proposal ${proposal.id}`)
              io.write(`  ${proposal.description}`)
              io.write(`  Ops (${proposal.ops.length}): ${proposal.ops.map(o => o.type).join(', ')}`)
              io.write('  Approve? [y/N]')
              const answer = (await io.prompt()).trim().toLowerCase()
              if (answer === 'y') {
                await approveProposal(layout, proposal.id)
                io.write('  → Approved.')
              } else {
                await appendIntegrityLog(layout, {
                  event: 'EVOLUTION_REJECTED', id: proposal.id, digest: proposal.digest,
                  ts: new Date().toISOString(), reason: 'operator_declined',
                })
                io.write('  → Rejected.')
              }
            }
          }
        }

        // ── Sleep cycle ───────────────────────────────────────────────────────
        await runSleepCycle({
          layout,
          baseline,
          logger,
          sessionId:     currentSessionId,
          contextWindow: cpe.contextWindow,
          compact:       result.closed === 'normal' && result.compact,
          ...((result.closed === 'normal' || result.closed === 'reboot')
            ? { closurePayload: result.closurePayload }
            : {}),
        })

        if (result.closed !== 'reboot') break

        // ── Reboot: re-run boot, clear chat, start new session ───────────────
        const rebootResult = await startEntity({ layout, logger, io: bootIO, sleepCycle: runSleepCycle })
        if (!rebootResult.ok) {
          throw new CLIError(`Reboot boot failed (phase ${rebootResult.phase}): ${rebootResult.reason}`, 1)
        }
        currentSessionId   = rebootResult.sessionId
        currentContextMsgs = rebootResult.contextMessages

        // Clear chat visual and show fresh header for the new session
        tui?.clearChat()
        const newStats    = await loadEntityStats(layout, fcpVersion)
        const newHdrLines = renderHeader(newStats, cols)
        io.write(newHdrLines.join('\n'))
      }
    } finally {
      tui?.teardown()
    }
  } finally {
    shared?.rl.close()
  }
}

export { runFcp }

export function registerRun(program: Command): void {
  program
    .command('run')
    .description('Start an FCP session (default command)')
    .option('--verbose', 'Verbose logging')
    .action(async function (this: Command, opts: { verbose?: boolean }) {
      const entity = (this.optsWithGlobals() as { entity?: string }).entity
      await runFcp({ ...(entity ? { entity } : {}), ...(opts.verbose ? { verbose: true } : {}) })
    })
}
