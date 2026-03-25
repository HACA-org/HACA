import { existsSync } from 'node:fs'
import { readdir } from 'node:fs/promises'
import { join } from 'node:path'
import { randomUUID } from 'node:crypto'
import type { Layout } from '../store/layout.js'
import { readJson, writeJson, appendJsonl, ensureDir } from '../store/io.js'
import type { Logger } from '../logger/logger.js'
import type {
  EpisodicEntry,
  SemanticEntry,
  WorkingMemory,
  WorkingMemoryEntry,
  ClosurePayload,
} from './types.js'

const DEFAULT_MAX_ENTRIES = 50

export type MIL = ReturnType<typeof createMIL>

export function createMIL(layout: Layout, logger: Logger) {

  // --- Episodic ---

  async function writeEpisodic(sessionId: string, content: string, tags?: string[]): Promise<EpisodicEntry> {
    await ensureDir(layout.episodic)
    const entry: EpisodicEntry = {
      id: randomUUID(),
      sessionId,
      ts: new Date().toISOString(),
      content,
      tags,
    }
    const path = join(layout.episodic, `${entry.id}.json`)
    await writeJson(path, entry)
    await logger.info('mil', 'episodic_write', { id: entry.id, sessionId })
    return entry
  }

  async function readEpisodic(id: string): Promise<EpisodicEntry | null> {
    const path = join(layout.episodic, `${id}.json`)
    if (!existsSync(path)) return null
    return readJson<EpisodicEntry>(path)
  }

  // --- Semantic ---

  async function promoteToSemantic(episodicId: string, content: string, tags?: string[]): Promise<SemanticEntry> {
    await ensureDir(layout.semantic)
    const entry: SemanticEntry = {
      id: randomUUID(),
      ts: new Date().toISOString(),
      content,
      tags,
      promotedFrom: episodicId,
    }
    const path = join(layout.semantic, `${entry.id}.json`)
    await writeJson(path, entry)
    await logger.info('mil', 'semantic_promote', { id: entry.id, from: episodicId })
    return entry
  }

  async function readSemantic(id: string): Promise<SemanticEntry | null> {
    const path = join(layout.semantic, `${id}.json`)
    if (!existsSync(path)) return null
    return readJson<SemanticEntry>(path)
  }

  // --- Working Memory ---

  async function getWorkingMemory(): Promise<WorkingMemory> {
    if (!existsSync(layout.workingMemory)) {
      return { entries: [], maxEntries: DEFAULT_MAX_ENTRIES }
    }
    return readJson<WorkingMemory>(layout.workingMemory)
  }

  async function updateWorkingMemory(updates: WorkingMemoryEntry[]): Promise<void> {
    const wm = await getWorkingMemory()
    const existing = new Map(wm.entries.map(e => [e.id, e]))
    for (const u of updates) {
      existing.set(u.id, u)
    }
    const entries = Array.from(existing.values())
      .sort((a, b) => b.ts.localeCompare(a.ts))
      .slice(0, wm.maxEntries)
    await writeJson(layout.workingMemory, { ...wm, entries })
    await logger.info('mil', 'working_memory_updated', { count: entries.length })
  }

  // --- Recall tool ---

  async function recall(query: string): Promise<string> {
    const results: Array<{ layer: string; content: string; ts: string }> = []

    // 1. Working memory first
    const wm = await getWorkingMemory()
    for (const entry of wm.entries) {
      if (entry.summary.toLowerCase().includes(query.toLowerCase())) {
        results.push({ layer: 'working_memory', content: entry.summary, ts: entry.ts })
      }
    }

    // 2. Semantic
    if (existsSync(layout.semantic)) {
      const files = await readdir(layout.semantic)
      for (const file of files) {
        if (!file.endsWith('.json')) continue
        const entry = await readJson<SemanticEntry>(join(layout.semantic, file))
        if (entry.content.toLowerCase().includes(query.toLowerCase())) {
          results.push({ layer: 'semantic', content: entry.content, ts: entry.ts })
        }
      }
    }

    // 3. Episodic (most recent first, limit 10)
    if (existsSync(layout.episodic)) {
      const files = (await readdir(layout.episodic))
        .filter(f => f.endsWith('.json'))
        .sort()
        .reverse()
        .slice(0, 20)
      for (const file of files) {
        const entry = await readJson<EpisodicEntry>(join(layout.episodic, file))
        if (entry.content.toLowerCase().includes(query.toLowerCase())) {
          results.push({ layer: 'episodic', content: entry.content, ts: entry.ts })
          if (results.length >= 10) break
        }
      }
    }

    if (results.length === 0) return `No memories found for: ${query}`
    return results.map(r => `[${r.layer}] ${r.content}`).join('\n')
  }

  // --- Remember tool ---

  async function remember(sessionId: string, content: string, tags?: string[]): Promise<string> {
    const entry = await writeEpisodic(sessionId, content, tags)
    return `Remembered (episodic/${entry.id}): ${content.slice(0, 80)}`
  }

  // --- Closure Payload Processing ---

  async function processClosure(payload: ClosurePayload): Promise<void> {
    await logger.info('mil', 'closure_process_start', { sessionId: payload.sessionId })

    // Apply promotions episodic → semantic
    for (const promotion of payload.promotions) {
      await promoteToSemantic(promotion.episodicId, promotion.content, promotion.tags)
    }

    // Update working memory
    if (payload.workingMemoryUpdates.length > 0) {
      await updateWorkingMemory(payload.workingMemoryUpdates)
    }

    // Write session handoff
    if (payload.handoff) {
      await writeJson(layout.sessionHandoff, payload.handoff)
      await logger.info('mil', 'handoff_written', { sessionId: payload.handoff.sessionId })
    }

    // Append to session store
    await appendJsonl(layout.sessionStore, {
      type: 'closure_processed',
      ts: new Date().toISOString(),
      sessionId: payload.sessionId,
      promotions: payload.promotions.length,
      workingMemoryUpdates: payload.workingMemoryUpdates.length,
    })

    await logger.info('mil', 'closure_process_complete', { sessionId: payload.sessionId })
  }

  return {
    recall,
    remember,
    writeEpisodic,
    readEpisodic,
    promoteToSemantic,
    readSemantic,
    getWorkingMemory,
    updateWorkingMemory,
    processClosure,
  }
}
