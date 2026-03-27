// recall() — unified search across all 3 memory layers (working, semantic, episodic).
// createMemoryStore() — factory returning a MemoryStore bound to a layout + session.
import { writeEpisodic, rotateEpisodic, searchEpisodic } from './episodic.js'
import { writeSemantic, searchSemantic } from './semantic.js'
import { getWorkingMemory, setWorkingMemory, mergeWorkingMemory } from './working.js'
import type { Layout } from '../types/store.js'
import type { Logger } from '../types/logger.js'
import type { MemoryStore, RecallResult, RecallMatch } from '../types/mil.js'

export async function recall(layout: Layout, query: string): Promise<RecallResult> {
  const matches: RecallMatch[] = []
  const q = query.toLowerCase()

  // Working memory — highest relevance (actively pinned)
  const wm = await getWorkingMemory(layout)
  for (const entry of wm.entries) {
    if (entry.path.toLowerCase().includes(q)) {
      matches.push({ source: 'working', path: entry.path, relevance: 0.9 })
    }
  }

  // Semantic memory — promoted long-term knowledge
  for (const entry of await searchSemantic(layout, query)) {
    matches.push({ source: 'semantic', path: entry.path, relevance: 0.7 })
  }

  // Episodic memory — recent session fragments (lower relevance)
  for (const relPath of await searchEpisodic(layout, q)) {
    matches.push({ source: 'episodic', path: relPath, relevance: 0.5 })
  }

  if (matches.length === 0) return { found: false }
  return { found: true, matches: matches.sort((a, b) => b.relevance - a.relevance) }
}

export function createMemoryStore(layout: Layout, sessionId: string, _logger: Logger): MemoryStore {
  return {
    recall: (query)          => recall(layout, query),

    writeEpisodic: async (slug, content) => {
      const entry = await writeEpisodic(layout, sessionId, slug, content)
      await rotateEpisodic(layout)
      return entry
    },

    writeSemantic: (slug, content) => writeSemantic(layout, slug, content),

    // Promote slugs from episodic to semantic memory.
    promoteSlugs: async (slugs) => {
      for (const slug of slugs) {
        await writeSemantic(layout, slug, `# ${slug}\nPromoted from session ${sessionId}.`)
      }
    },

    getWorkingMemory: () => getWorkingMemory(layout),

    setWorkingMemory: (wm) => setWorkingMemory(layout, wm),
  }
}

// Process a ClosurePayload — called by CLI after normal session close.
export async function processClosure(
  layout: Layout,
  sessionId: string,
  logger: Logger,
  closure: {
    consolidation: string
    promotion:     string[]
    workingMemory: Array<{ priority: number; path: string }>
  },
  maxEntries: number,
): Promise<void> {
  const store = createMemoryStore(layout, sessionId, logger)
  const log   = logger.child({ module: 'mil', fn: 'processClosure' })

  try {
    // Write session consolidation to episodic
    if (closure.consolidation.trim()) {
      await store.writeEpisodic('consolidation', closure.consolidation)
    }

    // Promote requested slugs to semantic
    if (closure.promotion.length > 0) {
      await store.promoteSlugs(closure.promotion)
    }

    // Merge working memory updates
    if (closure.workingMemory.length > 0) {
      await mergeWorkingMemory(layout, closure.workingMemory, maxEntries)
    }
  } catch (e: unknown) {
    log.error('mil:closure:failed', { err: String(e) })
    throw e
  }
}
