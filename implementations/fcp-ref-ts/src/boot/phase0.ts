// Phase 0: Imprint Verification — validate memory/imprint.json and operator hash.
import { sha256Digest } from './integrity.js'
import { BootError } from '../types/boot.js'
import type { BootPhase, BootContext } from '../types/boot.js'

export const phase0: BootPhase = {
  id:   0,
  name: 'imprint-verification',
  async run(ctx: BootContext): Promise<void> {
    const { imprint, logger } = ctx
    const { operator_name, operator_email, operator_hash } = imprint.operator_bound
    const expected = sha256Digest(`${operator_name}\n${operator_email}`)
    if (operator_hash !== expected) {
      throw new BootError(0, 'Operator hash mismatch in imprint.json — entity may be compromised')
    }
    logger.info('boot:phase0:ok', { operator: operator_name })
  },
}
