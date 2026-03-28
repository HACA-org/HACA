// SIL Heartbeat — vital check registry + orchestrator.
// createHeartbeat is a factory (L2: no module-level state).
// Persistence: state/heartbeat.json tracks { lastTs, cycleCount } between sessions.
// shouldRun: cycle threshold OR elapsed interval from lastTs.
import { z } from 'zod'
import { fileExists, readJson, writeJson } from '../store/io.js'
import type { Layout }            from '../types/store.js'
import type { Baseline }          from '../types/formats/baseline.js'
import type { Logger }            from '../types/logger.js'
import type { VitalCheck, HeartbeatContext, HeartbeatResult } from '../types/sil.js'

const HeartbeatStateSchema = z.object({
  lastTs:     z.string().datetime(),
  cycleCount: z.number().int().nonnegative(),
})
type HeartbeatState = z.infer<typeof HeartbeatStateSchema>

async function loadState(layout: Layout): Promise<HeartbeatState> {
  if (!await fileExists(layout.state.heartbeat)) {
    return { lastTs: new Date(0).toISOString(), cycleCount: 0 }
  }
  try {
    return HeartbeatStateSchema.parse(await readJson(layout.state.heartbeat))
  } catch {
    return { lastTs: new Date(0).toISOString(), cycleCount: 0 }
  }
}

export interface Heartbeat {
  shouldRun(cycleCount: number): Promise<boolean>
  run(cycleCount: number, inputTokens: number): Promise<HeartbeatResult>
}

export function createHeartbeat(
  layout:   Layout,
  baseline: Baseline,
  logger:   Logger,
  checks:   VitalCheck[],
): Heartbeat {
  const { cycleThreshold, intervalSeconds } = baseline.heartbeat

  return {
    async shouldRun(cycleCount: number): Promise<boolean> {
      const state = await loadState(layout)
      const cycleDue = (cycleCount - state.cycleCount) >= cycleThreshold
      const elapsed  = Date.now() - new Date(state.lastTs).getTime()
      const timeDue  = elapsed >= intervalSeconds * 1000
      return cycleDue || timeDue
    },

    async run(cycleCount: number, inputTokens: number): Promise<HeartbeatResult> {
      const ts      = new Date().toISOString()
      const budgetPct = baseline.contextWindow.budgetTokens > 0
        ? Math.round((inputTokens / baseline.contextWindow.budgetTokens) * 100)
        : 0

      const ctx: HeartbeatContext = {
        layout,
        baseline,
        logger,
        cycleCount,
        lastHeartbeatTs: ts,
        inputTokens,
      }

      const vitals: Array<{ check: string } & (import('../types/sil.js').VitalResult)> = []
      for (const check of checks) {
        try {
          const result = await check.run(ctx)
          vitals.push({ check: check.name, ...result })
        } catch (e: unknown) {
          logger.warn(`sil:heartbeat:check_error:${check.name}`, { error: String(e) })
          vitals.push({ check: check.name, ok: false, severity: 'degraded', message: String(e) })
        }
      }

      const criticals = vitals.filter(v => !v.ok && v.severity === 'critical')
      logger.info('sil:heartbeat', { cycleCount, budgetPct, vitals: vitals.length, criticals: criticals.length })

      // Persist updated state
      await writeJson(layout.state.heartbeat, { lastTs: ts, cycleCount } satisfies HeartbeatState)

      return { ts, cycleCount, inputTokens, budgetPct, vitals }
    },
  }
}

// Default set of vital checks for convenience.
export { budgetCheck }   from './checks/budget.js'
export { focusCheck }    from './checks/focus.js'
export { inboxCheck }    from './checks/inbox.js'
export { identityCheck } from './checks/identity.js'
