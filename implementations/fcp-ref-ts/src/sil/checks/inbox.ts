// Vital check: presession buffer — warn if io/inbox/presession/ exceeds max_entries.
import * as fs from 'node:fs/promises'
import { fileExists } from '../../store/io.js'
import type { VitalCheck, HeartbeatContext, VitalResult } from '../../types/sil.js'

export const inboxCheck: VitalCheck = {
  name: 'presession_buffer',
  async run(ctx: HeartbeatContext): Promise<VitalResult> {
    if (!await fileExists(ctx.layout.io.presession)) return { ok: true }

    let count: number
    try {
      const entries = await fs.readdir(ctx.layout.io.presession)
      count = entries.filter(e => e.endsWith('.msg')).length
    } catch {
      return { ok: true }
    }

    const max = ctx.baseline.preSessionBuffer.maxEntries
    if (count > max) {
      return {
        ok:       false,
        severity: 'degraded',
        message:  `presession buffer overflow: ${count} messages (max: ${max})`,
      }
    }
    return { ok: true }
  },
}
