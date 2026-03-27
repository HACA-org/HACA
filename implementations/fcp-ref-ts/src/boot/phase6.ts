// Phase 6: Critical Condition Check — distress beacon and pending SIL alerts.
import { fileExists } from '../store/io.js'
import { BootError } from '../types/boot.js'
import type { BootPhase, BootContext } from '../types/boot.js'

export const phase6: BootPhase = {
  id:   6,
  name: 'vital-status',
  async run(ctx: BootContext): Promise<void> {
    const { layout, logger } = ctx

    if (await fileExists(layout.state.distressBeacon)) {
      throw new BootError(
        6,
        'Distress beacon is active — resolve the condition and remove state/distress.beacon before booting',
      )
    }

    // TODO (SIL Fase 7): check sil.log for DRIFT_FAULT, IDENTITY_DRIFT, SIL_UNRESPONSIVE,
    // SEVERANCE_PENDING. For now the check is limited to the beacon file.

    logger.info('boot:phase6:ok')
  },
}
