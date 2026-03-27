// Vital check: context budget — warn/critical when token usage exceeds thresholds.
import type { VitalCheck, HeartbeatContext, VitalResult } from '../../types/sil.js'

export const budgetCheck: VitalCheck = {
  name: 'context_budget',
  async run(ctx: HeartbeatContext): Promise<VitalResult> {
    const budget   = ctx.baseline.context_window.budget_tokens
    const critical = ctx.baseline.context_window.critical_pct
    if (budget <= 0) return { ok: true }

    const pct  = (ctx.inputTokens / budget) * 100
    const warn = critical - 10

    if (pct >= critical) {
      return {
        ok:       false,
        severity: 'critical',
        message:  `context budget critical: ${pct.toFixed(1)}% used (threshold: ${critical}%)`,
      }
    }
    if (pct >= warn) {
      return {
        ok:       false,
        severity: 'degraded',
        message:  `context budget warning: ${pct.toFixed(1)}% used (warn at: ${warn}%)`,
      }
    }
    return { ok: true }
  },
}
