// Working memory — active pointer map (priority-ranked paths).
// Single JSON file: memory/working-memory.json  schema: WorkingMemorySchema.
import { ensureDir, fileExists, readJson, writeJson } from '../store/io.js'
import { parseWorkingMemory } from '../store/parse.js'
import { MILError } from '../types/mil.js'
import type { Layout } from '../types/store.js'
import type { WorkingMemory, WorkingMemoryEntry } from '../types/formats/memory.js'

export async function getWorkingMemory(layout: Layout): Promise<WorkingMemory> {
  if (!await fileExists(layout.memory.workingMemory)) return { version: '1.0', entries: [] }
  try {
    return parseWorkingMemory(await readJson(layout.memory.workingMemory))
  } catch (e: unknown) {
    throw new MILError('Failed to read working-memory.json', e)
  }
}

export async function setWorkingMemory(layout: Layout, wm: WorkingMemory): Promise<void> {
  await ensureDir(layout.memory.dir)
  await writeJson(layout.memory.workingMemory, wm)
}

// Merge new entries into working memory and prune to maxEntries, keeping highest priority.
export async function mergeWorkingMemory(
  layout: Layout,
  incoming: WorkingMemoryEntry[],
  maxEntries: number,
): Promise<void> {
  const existing = await getWorkingMemory(layout)
  // Deduplicate by path — incoming overrides existing for the same path.
  const byPath = new Map(existing.entries.map(e => [e.path, e]))
  for (const e of incoming) byPath.set(e.path, e)
  const merged = [...byPath.values()]
    .sort((a, b) => b.priority - a.priority)
    .slice(0, maxEntries)
  await setWorkingMemory(layout, { version: '1.0', entries: merged })
}
