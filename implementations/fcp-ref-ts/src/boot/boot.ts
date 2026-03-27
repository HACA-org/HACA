// Boot orchestrator — iterates BOOT_PHASES[], builds BootContext, returns BootResult.
// Detects cold-start (imprint.json absent) and delegates to runFAP.
import { fileExists, readJson } from '../store/io.js'
import { parseBaseline, parseImprintRecord } from '../store/parse.js'
import { runFAP } from './fap.js'
import { BOOT_PHASES } from './phases.js'
import { BootError } from '../types/boot.js'
import type { BootContext, BootResult, StartEntityOptions } from '../types/boot.js'
import type { CPEMessage } from '../types/cpe.js'

export async function startEntity(opts: StartEntityOptions): Promise<BootResult> {
  const { layout, logger, io, sleepCycle } = opts
  const log = logger.child({ module: 'boot' })

  // ── Cold-start: run FAP ──────────────────────────────────────────────────
  if (!await fileExists(layout.memory.imprint)) {
    if (!opts.operatorName || !opts.operatorEmail) {
      return { ok: false, phase: 0, reason: 'Entity not initialized — run: fcp init' }
    }
    log.info('boot:cold-start')
    const result = await runFAP({
      layout,
      operatorName: opts.operatorName,
      operatorEmail: opts.operatorEmail,
      logger,
      io,
    })
    if (!result.ok) return { ok: false, phase: 0, reason: result.reason }
    return { ok: true, sessionId: result.sessionId, contextMessages: [] }
  }

  // ── Warm boot: load context and run phases ───────────────────────────────
  log.info('boot:warm-start')

  let baseline
  let imprint
  try {
    baseline = parseBaseline(await readJson(layout.state.baseline))
    imprint  = parseImprintRecord(await readJson(layout.memory.imprint))
  } catch (e: unknown) {
    return { ok: false, phase: 0, reason: `Failed to load boot context: ${String(e)}` }
  }

  const ctx: BootContext = {
    layout, baseline, imprint, logger: log, io,
    ...(sleepCycle ? { sleepCycle } : {}),
  }

  let contextMessages: CPEMessage[] = []
  let sessionId: string | undefined

  for (const phase of BOOT_PHASES) {
    try {
      const payload = await phase.run(ctx)
      if (payload?.contextMessages) contextMessages = payload.contextMessages
      if (payload?.sessionId)       sessionId = payload.sessionId
    } catch (e: unknown) {
      if (e instanceof BootError) {
        return { ok: false, phase: e.phase, reason: e.message }
      }
      return { ok: false, phase: phase.id, reason: String(e) }
    }
  }

  if (!sessionId) {
    return { ok: false, phase: 7, reason: 'Boot complete but no session token was issued' }
  }

  log.info('boot:complete', { sessionId })
  return { ok: true, sessionId, contextMessages }
}
