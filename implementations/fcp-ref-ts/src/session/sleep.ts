// Sleep cycle — post-session consolidation.
// Writes session_close event, removes session token.
// MIL processing (episodic write, semantic promotion) added in Fase 5.
import * as fs from 'node:fs/promises'
import { appendJsonl } from '../store/io.js'
import type { Layout } from '../types/store.js'
import type { Baseline } from '../types/formats/baseline.js'
import type { Logger } from '../types/logger.js'

// Matches SleepCycleFn signature from types/boot.ts.
export async function runSleepCycle(
  layout: Layout,
  _baseline: Baseline,
  logger: Logger,
): Promise<void> {
  logger.info('sleep:start')
  const ts = new Date().toISOString()

  await appendJsonl(layout.memory.sessionJsonl, {
    type:   'session_close',
    ts,
    reason: 'normal',
  })

  // Remove session token — entity is no longer active until next boot.
  await fs.unlink(layout.state.sentinels.sessionToken).catch(() => undefined)

  logger.info('sleep:complete')
}
