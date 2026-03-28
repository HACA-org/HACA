// Sleep Cycle orchestrator — runs after every session close.
// Three sequential stages (HACA-Arch §6.4):
//   1. Memory consolidation (MIL) — transfer session data to long-term stores
//   2. Garbage collection     (MIL) — compact session history if triggered by compact protocol
//   3. Endure execution       (SIL) — process queued evolution proposals, if any
//
// Token is revoked at start; no Cognitive Cycles run during this window.
import * as fs from 'node:fs/promises'
import { appendJsonl } from '../store/io.js'
import { processClosure, compactSessionHistory } from '../mil/mil.js'
import { runEndureProtocol } from '../sil/sil.js'
import type { SleepCycleOpts } from '../types/boot.js'

export async function runSleepCycle(opts: SleepCycleOpts): Promise<void> {
  const { layout, baseline, logger, sessionId, closurePayload, contextWindow, compact } = opts
  const log = logger.child({ module: 'sleep' })
  log.info('sleep:start')

  // ── Revoke session token ────────────────────────────────────────────────────
  await fs.unlink(layout.state.sentinels.sessionToken).catch(() => undefined)

  await appendJsonl(layout.memory.sessionJsonl, {
    type:   'session_close',
    ts:     new Date().toISOString(),
    reason: compact ? 'compact' : 'normal',
  })

  // ── Stage 1: Memory consolidation (MIL) ────────────────────────────────────
  if (closurePayload) {
    log.info('sleep:consolidation:start')
    try {
      await processClosure(
        layout,
        sessionId,
        logger,
        closurePayload,
        baseline.workingMemory.maxEntries,
      )
      log.info('sleep:consolidation:ok')
    } catch (e: unknown) {
      // Log and continue — consolidation failure must not block GC or Endure
      log.error('sleep:consolidation:failed', { err: String(e) })
    }
  } else {
    log.warn('sleep:consolidation:skipped', { reason: 'no closure payload' })
  }

  // ── Stage 2: Garbage collection (MIL) ──────────────────────────────────────
  if (compact) {
    log.info('sleep:gc:start')
    try {
      await compactSessionHistory(layout, contextWindow, logger)
      log.info('sleep:gc:ok')
    } catch (e: unknown) {
      log.error('sleep:gc:failed', { err: String(e) })
    }
  }

  // ── Stage 3: Endure execution (SIL) ────────────────────────────────────────
  try {
    await runEndureProtocol(layout, logger)
  } catch (e: unknown) {
    log.error('sleep:endure:failed', { err: String(e) })
  }

  log.info('sleep:complete')
}
