// Drain the async stimuli inbox at the start of each cycle.
// Only reads from io/inbox/ — io/inbox/presession/ is drained at boot (Phase 5).
import * as fs from 'node:fs/promises'
import { fileExists, drainMsgDir } from '../store/io.js'
import type { Layout } from '../types/store.js'
import type { CPEMessage } from '../types/cpe.js'

export async function drainInbox(layout: Layout): Promise<CPEMessage[]> {
  if (!await fileExists(layout.io.inbox)) return []
  const items = await drainMsgDir(layout.io.inbox)
  const messages: CPEMessage[] = []
  for (const { file, raw } of items) {
    const text = typeof raw === 'string' ? raw : JSON.stringify(raw, null, 2)
    messages.push({ role: 'user', content: text })
    await fs.unlink(file).catch(() => undefined)
  }
  return messages
}
