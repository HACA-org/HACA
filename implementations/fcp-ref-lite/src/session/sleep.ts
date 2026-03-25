import type { Layout } from '../store/layout.js'
import { writeJson, appendJsonl, removeFile } from '../store/io.js'
import type { Logger } from '../logger/logger.js'
import type { Message } from '../cpe/types.js'

export interface ClosurePayload {
  ts: string
  sessionId: string
  messageCount: number
  summary: string[]
}

export async function runSleepCycle(
  layout: Layout,
  sessionId: string,
  messages: Message[],
  logger: Logger,
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
  }

  await writeJson(layout.pendingClosure, closure)
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
