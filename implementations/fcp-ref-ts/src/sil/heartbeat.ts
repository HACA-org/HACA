// SIL Heartbeat — vital check registry + orchestrator.
// createHeartbeat is a factory (L2: no module-level state).
// shouldRun: cycle threshold OR elapsed interval from lastHeartbeatTs.
import type { Layout }            from '../types/store.js'
import type { Baseline }          from '../types/formats/baseline.js'
import type { Logger }            from '../types/logger.js'
import type { VitalCheck, HeartbeatContext, HeartbeatResult } from '../types/sil.js'

export interface Heartbeat {
  shouldRun(cycleCount: number, lastHeartbeatTs: string): boolean
  run(cycleCount: number, inputTokens: number, lastHeartbeatTs: string): Promise<HeartbeatResult>
}

export function createHeartbeat(
  layout:   Layout,
  baseline: Baseline,
  logger:   Logger,
  checks:   VitalCheck[],
): Heartbeat {
  const { cycleThreshold, intervalSeconds } = baseline.heartbeat

  return {
    shouldRun(cycleCount: number, lastHeartbeatTs: string): boolean {
      const cycleDue = cycleCount >= cycleThreshold
      const elapsed  = Date.now() - new Date(lastHeartbeatTs).getTime()
      const timeDue  = elapsed >= intervalSeconds * 1000
      return cycleDue || timeDue
    },

    async run(cycleCount, inputTokens, lastHeartbeatTs): Promise<HeartbeatResult> {
      const ts      = new Date().toISOString()
      const budgetPct = baseline.contextWindow.budgetTokens > 0
        ? Math.round((inputTokens / baseline.contextWindow.budgetTokens) * 100)
        : 0

      const ctx: HeartbeatContext = {
        layout,
        baseline,
        logger,
        cycleCount,
        lastHeartbeatTs,
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

      return { ts, cycleCount, inputTokens, budgetPct, vitals }
    },
  }
}

// Default set of vital checks for convenience.
export { budgetCheck }   from './checks/budget.js'
export { focusCheck }    from './checks/focus.js'
export { inboxCheck }    from './checks/inbox.js'
export { identityCheck } from './checks/identity.js'
