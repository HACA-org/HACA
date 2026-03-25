import { existsSync } from 'node:fs'
import type { Layout } from '../store/layout.js'
import { appendJsonl, removeFile, readJson } from '../store/io.js'
import type { Logger } from '../logger/logger.js'
import type { Message } from '../cpe/types.js'
import { createMIL } from '../mil/mil.js'
import type { ClosurePayload } from '../mil/types.js'
import { runEndureProtocol } from '../sil/endure.js'
import { logSleepComplete } from '../sil/chain.js'
import type { ImprintRecord } from '../boot/types.js'

export type { ClosurePayload }

export async function runSleepCycle(
  layout: Layout,
  sessionId: string,
  messages: Message[],
  logger: Logger,
  closurePayload?: Partial<Pick<ClosurePayload, 'workingMemoryUpdates' | 'handoff' | 'promotions'>>,
): Promise<void> {
  await logger.info('sleep', 'start', { sessionId })

  const closure: ClosurePayload = {
    ts: new Date().toISOString(),
    sessionId,
    messageCount: messages.length,
    summary: messages
      .filter(m => m.role === 'assistant')
      .map(m => typeof m.content === 'string' ? m.content.slice(0, 200) : '')
      .filter(Boolean)
      .slice(-3),
    workingMemoryUpdates: closurePayload?.workingMemoryUpdates ?? [],
    handoff: closurePayload?.handoff,
    promotions: closurePayload?.promotions ?? [],
  }

  // Normal close: process closure immediately via MIL
  const mil = createMIL(layout, logger)
  await mil.processClosure(closure)

  // Endure protocol: process approved proposals (skill installs, etc.)
  let profile: 'haca-core' | 'haca-evolve' = 'haca-core'
  if (existsSync(layout.imprint)) {
    try {
      const imprint = await readJson<ImprintRecord>(layout.imprint)
      profile = imprint.hacaProfile
    } catch { /* use default */ }
  }
  await runEndureProtocol(layout, logger, profile)

  await appendJsonl(layout.sessionStore, {
    type: 'session_close',
    ts: closure.ts,
    sessionId,
    messageCount: messages.length,
  })

  await logSleepComplete(layout, sessionId)
  await removeFile(layout.sessionToken)
  await logger.info('sleep', 'complete', { sessionId })
  await logger.increment('cycles')
}
