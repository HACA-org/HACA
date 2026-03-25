import type { Layout } from '../store/layout.js'
import { appendJsonl, removeFile } from '../store/io.js'
import type { Logger } from '../logger/logger.js'
import type { Message } from '../cpe/types.js'
import { createMIL } from '../mil/mil.js'
import type { ClosurePayload } from '../mil/types.js'

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

  await appendJsonl(layout.sessionStore, {
    type: 'session_close',
    ts: closure.ts,
    sessionId,
    messageCount: messages.length,
  })

  await removeFile(layout.sessionToken)
  await logger.info('sleep', 'complete', { sessionId })
  await logger.increment('cycles')
}
