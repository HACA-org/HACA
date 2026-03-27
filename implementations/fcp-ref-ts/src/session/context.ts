// Build the CPE system prompt from boot.md and persona/*.md.
// Called once at session start; result is reused across all cycles.
import * as fs from 'node:fs/promises'
import * as path from 'node:path'
import { fileExists } from '../store/io.js'
import type { Layout } from '../types/store.js'

export interface BuiltContext {
  readonly system: string
}

export async function buildContext(layout: Layout): Promise<BuiltContext> {
  const sections: string[] = []

  // boot.md — operator-managed custom instructions
  if (await fileExists(layout.bootMd)) {
    const content = await fs.readFile(layout.bootMd, 'utf8')
    if (content.trim()) sections.push(content.trim())
  }

  // persona/*.md — identity and behavioral files (sorted, non-recursive)
  const personaEntries = await safeReaddir(layout.persona)
  const mdFiles = personaEntries
    .filter(e => !e.isDirectory() && e.name.endsWith('.md'))
    .sort((a, b) => a.name.localeCompare(b.name))

  for (const entry of mdFiles) {
    const content = await fs.readFile(path.join(layout.persona, entry.name), 'utf8')
    if (content.trim()) sections.push(content.trim())
  }

  return { system: sections.join('\n\n---\n\n') }
}

async function safeReaddir(dirPath: string): Promise<import('node:fs').Dirent[]> {
  try {
    return await fs.readdir(dirPath, { withFileTypes: true })
  } catch {
    return []
  }
}
