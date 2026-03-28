// Vital check: context budget — warn/critical when token usage exceeds operator thresholds.
// Uses the model's actual context window (ctx.contextWindow) as denominator.
// criticalPct and warnPct are operator-visible thresholds (relative to 95% of the model window).
import type { VitalCheck, HeartbeatContext, VitalResult } from '../../types/sil.js'

export const budgetCheck: VitalCheck = {
  name: 'context_budget',
  async run(ctx: HeartbeatContext): Promise<VitalResult> {
    if (ctx.contextWindow <= 0) return { ok: true }

    // Operator sees 0-100% relative to 95% of the model window.
    const operatorMax = ctx.contextWindow * 0.95
    const pct         = (ctx.inputTokens / operatorMax) * 100
    const critical    = ctx.baseline.contextWindow.criticalPct
    const warn        = ctx.baseline.contextWindow.warnPct

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
