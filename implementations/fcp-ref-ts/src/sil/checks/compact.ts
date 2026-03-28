// Vital check: compact session — fires at 97% of the model context window.
// When triggered the loop injects a compact request into the CPE inbox.
// This threshold is intentionally above the operator-visible 100% (95% of window)
// to give the CPE a last chance to produce a Closure Payload before the window is full.
import type { VitalCheck, HeartbeatContext, VitalResult } from '../../types/sil.js'

export const COMPACT_THRESHOLD_PCT = 97

export const compactCheck: VitalCheck = {
  name: 'compact_session',
  async run(ctx: HeartbeatContext): Promise<VitalResult> {
    if (ctx.contextWindow <= 0) return { ok: true }

    const pct = (ctx.inputTokens / ctx.contextWindow) * 100

    if (pct >= COMPACT_THRESHOLD_PCT) {
      return {
        ok:       false,
        severity: 'critical',
        message:  `compact_session:${pct.toFixed(1)}%`,
      }
    }
    return { ok: true }
  },
}
