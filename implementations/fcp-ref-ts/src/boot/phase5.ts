// Phase 5: Context Assembly — build initial CPEMessage[] for the session loop.
// Collects pre-session stimuli (inbox/presession/) and working memory pointers.
import * as fs from 'node:fs/promises'
import { fileExists, drainMsgDir, readJson } from '../store/io.js'
import { parseWorkingMemory } from '../store/parse.js'
import type { BootPhase, BootContext, BootPhasePayload } from '../types/boot.js'
import type { CPEMessage } from '../types/cpe.js'

export const phase5: BootPhase = {
  id:   5,
  name: 'context-assembly',
  async run(ctx: BootContext): Promise<BootPhasePayload> {
    const { layout, logger } = ctx
    const contextMessages: CPEMessage[] = []

    // Drain pre-session inbox — stimuli queued without an active session.
    if (await fileExists(layout.io.presession)) {
      for (const { file, raw } of await drainMsgDir(layout.io.presession)) {
        const text = typeof raw === 'string' ? raw : JSON.stringify(raw, null, 2)
        contextMessages.push({ role: 'user', content: text })
        await fs.unlink(file).catch(() => undefined)
      }
    }

    // Working memory — inject active pointer map as context.
    if (await fileExists(layout.memory.workingMemory)) {
      const raw = await readJson(layout.memory.workingMemory)
      const wm = parseWorkingMemory(raw)
      if (wm.entries.length > 0) {
        const body = wm.entries
          .sort((a, b) => a.priority - b.priority)
          .map(e => `[${e.priority}] ${e.path}`)
          .join('\n')
        contextMessages.push({ role: 'user', content: `Working memory:\n${body}` })
      }
    }

    logger.info('boot:phase5:ok', { messages: contextMessages.length })
    return { contextMessages }
  },
}
