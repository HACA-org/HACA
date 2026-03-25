import { existsSync } from 'node:fs'
import { readFile, readdir } from 'node:fs/promises'
import { join } from 'node:path'
import type { Layout } from '../store/layout.js'
import { readJson, readJsonl } from '../store/io.js'

export interface BuiltContext {
  systemPrompt: string
  preSessionStimuli: unknown[]
}

async function readTextFile(path: string): Promise<string | null> {
  if (!existsSync(path)) return null
  return readFile(path, 'utf8')
}

async function readPersona(layout: Layout): Promise<string> {
  if (!existsSync(layout.persona)) return ''
  const files = (await readdir(layout.persona)).sort()
  const parts: string[] = []
  for (const file of files) {
    if (!file.endsWith('.md')) continue
    const content = await readFile(join(layout.persona, file), 'utf8')
    parts.push(`## ${file.replace('.md', '')}\n${content.trim()}`)
  }
  return parts.join('\n\n')
}

async function readWorkingMemory(layout: Layout): Promise<string> {
  if (!existsSync(layout.workingMemory)) return ''
  const wm = await readJson<{ entries?: Array<{ content: string }> }>(layout.workingMemory)
  const entries = wm.entries ?? []
  if (entries.length === 0) return ''
  const lines = entries.map(e => `- ${e.content}`)
  return `## Working Memory\n${lines.join('\n')}`
}

async function drainPresessionInbox(layout: Layout): Promise<unknown[]> {
  if (!existsSync(layout.inboxPresession)) return []
  const files = await readdir(layout.inboxPresession)
  const stimuli: unknown[] = []
  for (const file of files) {
    if (!file.endsWith('.json')) continue
    try {
      const data = await readJson(join(layout.inboxPresession, file))
      stimuli.push(data)
    } catch {
      // skip malformed files
    }
  }
  return stimuli
}

export async function buildContext(layout: Layout): Promise<BuiltContext> {
  const [protocol, persona, bootMd, workingMemory, preSessionStimuli] = await Promise.all([
    readTextFile(join(layout.root, 'src', 'protocol.md')),
    readPersona(layout),
    readTextFile(layout.bootMd),
    readWorkingMemory(layout),
    drainPresessionInbox(layout),
  ])

  const sections: string[] = []

  if (protocol) sections.push(`# FCP Protocol\n${protocol.trim()}`)
  if (persona) sections.push(`# Persona\n${persona}`)
  if (bootMd) sections.push(`# Operator Instructions\n${bootMd.trim()}`)
  if (workingMemory) sections.push(workingMemory)

  return {
    systemPrompt: sections.join('\n\n---\n\n'),
    preSessionStimuli,
  }
}
