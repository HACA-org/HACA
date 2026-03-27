// Phase 1: Host Introspection — verify baseline topology matches imprint profile.
import { BootError } from '../types/boot.js'
import type { BootPhase, BootContext } from '../types/boot.js'

export const phase1: BootPhase = {
  id:   1,
  name: 'host-introspection',
  async run(ctx: BootContext): Promise<void> {
    const { baseline, imprint, logger } = ctx
    if (imprint.haca_profile === 'haca-core' && baseline.cpe.topology !== 'transparent') {
      throw new BootError(1, `HACA-Core requires transparent topology, got: ${baseline.cpe.topology}`)
    }
    logger.info('boot:phase1:ok', { topology: baseline.cpe.topology, profile: imprint.haca_profile })
  },
}
