// Vital check: identity drift — re-verify state/integrity.json against current files.
import { verifyIntegrityDoc } from '../integrity.js'
import type { VitalCheck, HeartbeatContext, VitalResult } from '../../types/sil.js'

export const identityCheck: VitalCheck = {
  name: 'identity_drift',
  async run(ctx: HeartbeatContext): Promise<VitalResult> {
    const result = await verifyIntegrityDoc(ctx.layout)
    if (result.clean) return { ok: true }

    const summary = result.mismatches
      .slice(0, 3)
      .map(m => `${m.reason}: ${m.file}`)
      .join('; ')
    const extra = result.mismatches.length > 3
      ? ` (+${result.mismatches.length - 3} more)`
      : ''

    return {
      ok:       false,
      severity: 'critical',
      message:  `identity drift detected: ${summary}${extra}`,
    }
  },
}
