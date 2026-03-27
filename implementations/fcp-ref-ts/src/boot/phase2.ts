// Phase 2: Crash Recovery — detect stale session token and run sleep cycle.
import * as fs from 'node:fs/promises'
import { fileExists } from '../store/io.js'
import type { BootPhase, BootContext } from '../types/boot.js'

export const phase2: BootPhase = {
  id:   2,
  name: 'crash-recovery',
  async run(ctx: BootContext): Promise<void> {
    const { layout, baseline, logger, sleepCycle } = ctx
    if (!await fileExists(layout.state.sentinels.sessionToken)) return

    // Stale session token = prior session did not close cleanly.
    logger.warn('boot:phase2:crash-detected')
    await fs.unlink(layout.state.sentinels.sessionToken)

    if (sleepCycle) {
      logger.info('boot:phase2:sleep-cycle-start')
      await sleepCycle(layout, baseline, logger)
      logger.info('boot:phase2:sleep-cycle-done')
    }

    logger.info('boot:phase2:ok', { crashRecovered: true })
  },
}
