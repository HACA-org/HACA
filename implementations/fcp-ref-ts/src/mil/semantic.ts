// Semantic memory — promoted long-term knowledge.
// Files live in memory/semantic/<slug>.md — one file per concept/topic.
import * as fs from 'node:fs/promises'
import * as path from 'node:path'
import { ensureDir } from '../store/io.js'
import type { Layout } from '../types/store.js'
import type { SemanticEntry } from '../types/mil.js'

export async function writeSemantic(
  layout: Layout,
  slug: string,
  content: string,
): Promise<SemanticEntry> {
  await ensureDir(layout.memory.semantic)
  const filePath = path.join(layout.memory.semantic, `${slug}.md`)
  await fs.writeFile(filePath, content, 'utf8')
  const ts = new Date().toISOString()
  return { slug, path: path.relative(layout.root, filePath), ts }
}

// Substring search across all semantic files — filename and content.
// Reference impl uses simple string matching; production would use vector embeddings.
export async function searchSemantic(layout: Layout, query: string): Promise<SemanticEntry[]> {
  let entries: import('node:fs').Dirent[]
  try {
    entries = await fs.readdir(layout.memory.semantic, { withFileTypes: true })
  } catch {
    return []
  }
  const results: SemanticEntry[]  = []
  const q = query.toLowerCase()
  for (const entry of entries) {
    if (entry.isDirectory() || !entry.name.endsWith('.md')) continue
    const filePath = path.join(layout.memory.semantic, entry.name)
    const content  = await fs.readFile(filePath, 'utf8').catch(() => '')
    if (entry.name.toLowerCase().includes(q) || content.toLowerCase().includes(q)) {
      const stat = await fs.stat(filePath).catch(() => null)
      const ts   = stat?.mtime.toISOString() ?? new Date().toISOString()
      results.push({ slug: entry.name.replace(/\.md$/, ''), path: path.relative(layout.root, filePath), ts })
    }
  }
  return results
}
