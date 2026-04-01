// fcp_memory_write — MIL tool: write an episodic memory entry.
// If the slug already exists, returns the existing content and asks the CPE
// to decide: call again with overwrite:true to replace, or use a different slug.
import * as fs from 'node:fs/promises'
import * as path from 'node:path'
import { writeEpisodic } from '../episodic.js'
import type { ToolHandler, ToolResult, ExecContext } from '../../types/exec.js'

export const memoryWriteHandler: ToolHandler = {
  name: 'fcp_memory_write',
  description: 'Write an episodic memory entry to memory/episodic/<session>/<slug>.md. If the slug already exists in this session, returns the existing content — call again with overwrite:true to replace it, or choose a different slug.',
  inputSchema: {
    type: 'object',
    properties: {
      slug:      { type: 'string',  description: 'Entry identifier (lowercase alphanumeric and hyphens only).' },
      content:   { type: 'string',  description: 'Markdown content of the memory entry.' },
      overwrite: { type: 'boolean', description: 'Set to true to overwrite an existing slug. Omit or false to be notified if the slug exists.' },
    },
    required: ['slug', 'content'],
  },
  async execute(params: unknown, ctx: ExecContext): Promise<ToolResult> {
    if (typeof params !== 'object' || params === null) {
      return { ok: false, error: 'slug and content are required' }
    }
    const p = params as Record<string, unknown>
    const slug      = typeof p['slug']      === 'string'  ? p['slug'].trim()      : null
    const content   = typeof p['content']   === 'string'  ? p['content'].trim()   : null
    const overwrite = typeof p['overwrite'] === 'boolean' ? p['overwrite']        : false

    if (!slug)    return { ok: false, error: 'slug is required' }
    if (!content) return { ok: false, error: 'content must not be empty' }
    if (!/^[a-z0-9-]+$/.test(slug)) return { ok: false, error: 'slug must be lowercase alphanumeric and hyphens only' }

    // Check if slug already exists in any episodic directory for this session
    const sessionDirPrefix = ctx.sessionId.slice(0, 8)
    let existingPath: string | null = null
    try {
      const dirs = await fs.readdir(ctx.layout.memory.episodic, { withFileTypes: true })
      const sessionDir = dirs
        .filter(d => d.isDirectory() && d.name.endsWith(`-${sessionDirPrefix}`))
        .map(d => d.name)
        .sort()
        .at(-1)
      if (sessionDir) {
        const candidate = path.join(ctx.layout.memory.episodic, sessionDir, `${slug}.md`)
        await fs.access(candidate)
        existingPath = candidate
      }
    } catch { /* not found — proceed with write */ }

    if (existingPath && !overwrite) {
      const existing = await fs.readFile(existingPath, 'utf8').catch(() => '')
      return {
        ok: true,
        output: [
          `SLUG_EXISTS: "${slug}" already has content in this session.`,
          'Call again with overwrite:true to replace it, or use a different slug.',
          '',
          '--- existing content ---',
          existing.trim(),
          '--- end ---',
        ].join('\n'),
      }
    }

    const entry = await writeEpisodic(ctx.layout, ctx.sessionId, slug, content)
    ctx.logger.info('mil:memory_write', { slug, path: entry.path, overwrite })
    return { ok: true, output: `Written: ${entry.path}` }
  },
}
