// Episodic memory — session fragment archive.
// Each session gets its own directory; rotateEpisodic() removes the oldest when > MAX_SESSIONS.
import * as fs from 'node:fs/promises'
import * as path from 'node:path'
import { ensureDir } from '../store/io.js'
import type { Layout } from '../types/store.js'
import type { EpisodicEntry } from '../types/mil.js'

const MAX_SESSIONS = 5

export async function writeEpisodic(
  layout: Layout,
  sessionId: string,
  slug: string,
  content: string,
): Promise<EpisodicEntry> {
  const ts = new Date().toISOString()
  const dirName = `${ts.slice(0, 10)}-${sessionId.slice(0, 8)}`
  const dir = path.join(layout.memory.episodic, dirName)
  await ensureDir(dir)
  const filePath = path.join(dir, `${slug}.md`)
  await fs.writeFile(filePath, content, 'utf8')
  const stat = await fs.stat(filePath)
  return {
    path:      path.relative(layout.root, filePath),
    ts,
    sessionId,
    sizeBytes: stat.size,
  }
}

// Prune old episodic session directories, keeping only the latest MAX_SESSIONS.
export async function rotateEpisodic(layout: Layout): Promise<void> {
  let entries: import('node:fs').Dirent[]
  try {
    entries = await fs.readdir(layout.memory.episodic, { withFileTypes: true })
  } catch {
    return
  }
  const dirs = entries
    .filter(e => e.isDirectory())
    .map(e => e.name)
    .sort()  // ISO-prefixed names sort chronologically

  for (const name of dirs.slice(0, Math.max(0, dirs.length - MAX_SESSIONS))) {
    await fs.rm(path.join(layout.memory.episodic, name), { recursive: true, force: true })
  }
}

// Search the last 3 episodic session dirs for files containing the query.
export async function searchEpisodic(layout: Layout, query: string): Promise<string[]> {
  let dirs: import('node:fs').Dirent[]
  try {
    dirs = await fs.readdir(layout.memory.episodic, { withFileTypes: true })
  } catch {
    return []
  }
  const results: string[] = []
  const recent = dirs.filter(d => d.isDirectory()).map(d => d.name).sort().slice(-3)
  for (const name of recent) {
    const dirPath = path.join(layout.memory.episodic, name)
    let files: import('node:fs').Dirent[]
    try { files = await fs.readdir(dirPath, { withFileTypes: true }) } catch { continue }
    for (const file of files.filter(f => !f.isDirectory())) {
      const fp = path.join(dirPath, file.name)
      const content = await fs.readFile(fp, 'utf8').catch(() => '')
      if (content.toLowerCase().includes(query)) {
        results.push(path.relative(layout.root, fp))
      }
    }
  }
  return results
}
