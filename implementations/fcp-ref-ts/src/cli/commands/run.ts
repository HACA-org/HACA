// fcp run — boot entity, run session loop, run sleep cycle.
// Wires: startEntity → runSessionLoop → runSleepCycle.
// TUI (Fase 9) replaces the inline stdin/stdout IO.
import * as path from 'node:path'
import * as os from 'node:os'
import * as fs from 'node:fs/promises'
import { existsSync } from 'node:fs'
import { createInterface } from 'node:readline'
import type { Command } from 'commander'
import { createLayout } from '../../types/store.js'
import { createLogger }  from '../../logger/logger.js'
import { parseBaseline } from '../../store/parse.js'
import { readJson, fileExists } from '../../store/io.js'
import { startEntity }   from '../../boot/boot.js'
import { resolveAdapter } from '../../cpe/resolve.js'
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

const FCP_HOME     = path.join(os.homedir(), '.fcp')
const ENTITIES_DIR = path.join(FCP_HOME, 'entities')
const DEFAULT_FILE = path.join(FCP_HOME, 'default')

async function resolveEntityRoot(entityId?: string): Promise<string> {
  if (entityId) {
    const root = path.join(ENTITIES_DIR, entityId)
    if (!existsSync(root)) throw new CLIError(`Entity not found: ${entityId}`, 1)
    return root
  }

  if (existsSync(DEFAULT_FILE)) {
    const id = (await fs.readFile(DEFAULT_FILE, 'utf8')).trim()
    if (id) {
      const root = path.join(ENTITIES_DIR, id)
      if (existsSync(root)) return root
    }
  }

  // Single entity fallback
  if (existsSync(ENTITIES_DIR)) {
    const entries = await fs.readdir(ENTITIES_DIR, { withFileTypes: true })
    const dirs = entries.filter(e => e.isDirectory())
    if (dirs.length === 1) return path.join(ENTITIES_DIR, dirs[0]!.name)
  }

  throw new CLIError('No entity found. Run `fcp init` to create one.', 1)
}

function makeConsoleIO(): SessionIO {
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

  return {
    prompt(): Promise<string> {
      process.stdout.write('\n> ')
      return new Promise<string>(resolve => {
        if (lineQueue.length > 0) {
          resolve(lineQueue.shift()!)
        } else {
          resolvers.push(resolve)
        }
      })
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

async function runFcp(opts: { entity?: string; verbose?: boolean }): Promise<void> {
  const entityRoot = await resolveEntityRoot(opts.entity)
  const layout     = createLayout(entityRoot)
  const logger     = createLogger(opts.verbose ? {} : { test: false })

  // Load and validate baseline
  if (!await fileExists(layout.state.baseline)) {
    throw new CLIError(`baseline.json not found at ${layout.state.baseline}. Run \`fcp init\`.`, 1)
  }
  const baselineRaw = await readJson(layout.state.baseline)
  const baseline    = parseBaseline(baselineRaw)

  // Boot — FAP on cold start, 8-phase sequence on warm start
  const io: import('../../types/boot.js').BootIO = {
    write:  (msg) => process.stdout.write(msg + '\n'),
    prompt: (_question) => Promise.resolve(''),  // boot prompts not used in CLI run
  }

  // Read operator credentials from staging file (if present — set during `fcp init`)
  const stagingPath = path.join(entityRoot, 'state', '.fap-operator.json')
  let operatorName: string | undefined
  let operatorEmail: string | undefined
  if (await fileExists(stagingPath)) {
    try {
      const creds = await readJson(stagingPath) as Record<string, string>
      operatorName  = creds['operatorName']
      operatorEmail = creds['operatorEmail']
    } catch { /* ignore */ }
  }

  const bootResult = await startEntity({
    layout, logger, io,
    sleepCycle:    runSleepCycle,
    ...(operatorName  ? { operatorName }  : {}),
    ...(operatorEmail ? { operatorEmail } : {}),
  })

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

  process.stdout.write(`FCP — ${profile} — session ${sessionId}\n`)
  process.stdout.write('Type your message and press Enter. Ctrl-C to force exit.\n\n')

  const result = await runSessionLoop({
    layout, baseline, cpe, policy, tools, logger,
    io:            makeConsoleIO(),
    sessionId,
    profile,
    contextWindow: cpe.contextWindow,
    ...(contextMessages ? { contextMessages } : {}),
  })

  // ── HACA-Core: present pending proposals for Operator approval ──────────────
  // HACA-Evolve proposals are auto-approved at queue time; skip the gate.
  // This gate runs synchronously on the terminal before the sleep cycle starts.
  if (!baseline.authorizationScope) {
    const pending = await readPendingProposals(layout)
    if (pending.length > 0) {
      process.stdout.write(`\n── Evolution Proposals (${pending.length}) ──\n`)
      for (const proposal of pending) {
        if (proposal.approvedAt) continue  // already approved in prior session
        process.stdout.write(`\nProposal ${proposal.id}\n`)
        process.stdout.write(`  ${proposal.description}\n`)
        process.stdout.write(`  Ops (${proposal.ops.length}): ${proposal.ops.map(o => o.type).join(', ')}\n`)
        process.stdout.write('  Approve? [y/N] ')
        const answer = await new Promise<string>(resolve => {
          const rl = createInterface({ input: process.stdin, output: process.stdout, terminal: false })
          rl.once('line', line => { rl.close(); resolve(line.trim().toLowerCase()) })
        })
        if (answer === 'y') {
          await approveProposal(layout, proposal.id)
          await appendIntegrityLog(layout, {
            event: 'EVOLUTION_AUTH', id: proposal.id, digest: proposal.digest,
            ts: new Date().toISOString(), autoApproved: false,
          })
          process.stdout.write('  → Approved.\n')
        } else {
          await appendIntegrityLog(layout, {
            event: 'EVOLUTION_REJECTED', id: proposal.id, digest: proposal.digest,
            ts: new Date().toISOString(), reason: 'operator_declined',
          })
          process.stdout.write('  → Rejected.\n')
        }
      }
    }
  }

  // Sleep cycle: memory consolidation → GC → Endure (HACA-Arch §6.4)
  const sleepOpts = {
    layout,
    baseline,
    logger,
    sessionId,
    contextWindow: cpe.contextWindow,
    compact:       result.closed === 'normal' && result.compact,
    ...(result.closed === 'normal' ? { closurePayload: result.closurePayload } : {}),
  }
  await runSleepCycle(sleepOpts)
}

export { runFcp }

export function registerRun(program: Command): void {
  program
    .command('run')
    .description('Start an FCP session (default command)')
    .option('--entity <id>', 'Entity ID to run')
    .option('--verbose', 'Verbose logging')
    .action(async (opts: { entity?: string; verbose?: boolean }) => {
      await runFcp(opts)
    })
}
