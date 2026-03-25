import { existsSync } from 'node:fs'
import { readdir, unlink, stat } from 'node:fs/promises'
import { join } from 'node:path'
import type { Layout } from '../store/layout.js'
import { readJson, writeJson, removeFile } from '../store/io.js'
import type { Logger } from '../logger/logger.js'
import type { WorkingMemory } from './types.js'

const DEFAULT_MAX_EPISODIC = 200
const DEFAULT_MAX_WORKING_MEMORY = 50
const SESSION_JSONL_MAX_BYTES = 5 * 1024 * 1024 // 5MB

export interface GCOptions {
  maxEpisodic?: number
  maxWorkingMemory?: number
}

export async function runGC(layout: Layout, logger: Logger, opts: GCOptions = {}): Promise<void> {
  const maxEpisodic = opts.maxEpisodic ?? DEFAULT_MAX_EPISODIC
  const maxWM = opts.maxWorkingMemory ?? DEFAULT_MAX_WORKING_MEMORY

  await logger.info('gc', 'start')

  // 1. Rotate episodic — keep most recent N, delete the rest
  if (existsSync(layout.episodic)) {
    const files = (await readdir(layout.episodic)).filter(f => f.endsWith('.json'))
    const entries: Array<{ file: string; ts: string }> = []
    for (const file of files) {
      try {
        const data = await readJson<{ ts?: string }>(join(layout.episodic, file))
        entries.push({ file, ts: data.ts ?? '' })
      } catch {
        entries.push({ file, ts: '' })
      }
    }
    entries.sort((a, b) => b.ts.localeCompare(a.ts)) // newest first
    const toDelete = entries.slice(maxEpisodic)
    for (const { file } of toDelete) {
      await unlink(join(layout.episodic, file))
    }
    if (toDelete.length > 0) {
      await logger.info('gc', 'episodic_pruned', { deleted: toDelete.length, kept: maxEpisodic })
    }
  }

  // 2. Prune working memory
  if (existsSync(layout.workingMemory)) {
    const wm = await readJson<WorkingMemory>(layout.workingMemory)
    if (wm.entries.length > maxWM) {
      const pruned = wm.entries
        .sort((a, b) => b.ts.localeCompare(a.ts))
        .slice(0, maxWM)
      await writeJson(layout.workingMemory, { ...wm, entries: pruned })
      await logger.info('gc', 'working_memory_pruned', { before: wm.entries.length, after: pruned.length })
    }
  }

  // 3. Rotate session.jsonl when it exceeds threshold
  if (existsSync(layout.sessionStore)) {
    const { size } = await stat(layout.sessionStore)
    if (size >= SESSION_JSONL_MAX_BYTES) {
      const rotated = `${layout.sessionStore}.1`
      // Remove previous rotation before renaming
      await removeFile(rotated)
      const { rename } = await import('node:fs/promises')
      await rename(layout.sessionStore, rotated)
      await logger.info('gc', 'session_store_rotated', { sizeBytes: size })
    }
  }

  // 4. Clear stale session-grants.json (always safe to clear between GC runs)
  if (existsSync(layout.sessionGrants)) {
    await removeFile(layout.sessionGrants)
    await logger.info('gc', 'session_grants_cleared')
  }

  // 5. Remove pending-closure.json if stale (present but no active session = orphaned crash artifact)
  if (existsSync(layout.pendingClosure) && !existsSync(layout.sessionToken)) {
    await removeFile(layout.pendingClosure)
    await logger.info('gc', 'stale_pending_closure_removed')
  }

  await logger.info('gc', 'complete')
}
