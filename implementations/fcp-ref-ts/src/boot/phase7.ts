// Phase 7: Session Token Issuance — write state/sentinels/session.token.
import { randomUUID } from 'node:crypto'
import { ensureDir, writeJson } from '../store/io.js'
import type { BootPhase, BootContext, BootPhasePayload } from '../types/boot.js'

export const phase7: BootPhase = {
  id:   7,
  name: 'session-token',
  async run(ctx: BootContext): Promise<BootPhasePayload> {
    const { layout, logger } = ctx
    const sessionId = randomUUID()
    const issuedAt = new Date().toISOString()
    await ensureDir(layout.state.sentinels.dir)
    await writeJson(layout.state.sentinels.sessionToken, { session_id: sessionId, issued_at: issuedAt })
    logger.info('boot:phase7:ok', { sessionId })
    return { sessionId }
  },
}
