// fcp_memory_write — MIL tool: write an episodic memory entry.
import { writeEpisodic } from '../episodic.js'
import type { ToolHandler, ToolResult, ExecContext } from '../../types/exec.js'

export const memoryWriteHandler: ToolHandler = {
  name: 'fcp_memory_write',
  description: 'Write an episodic memory entry to memory/episodic/<session>/<slug>.md. Use this to record observations, decisions, or important events during the session.',
  inputSchema: {
    type: 'object',
    properties: {
      slug:    { type: 'string', description: 'Entry identifier (lowercase alphanumeric and hyphens only).' },
      content: { type: 'string', description: 'Markdown content of the memory entry.' },
    },
    required: ['slug', 'content'],
  },
  async execute(params: unknown, ctx: ExecContext): Promise<ToolResult> {
    if (typeof params !== 'object' || params === null) {
      return { ok: false, error: 'slug and content are required' }
    }
    const p = params as Record<string, unknown>
    const slug    = typeof p['slug']    === 'string' ? p['slug'].trim()    : null
    const content = typeof p['content'] === 'string' ? p['content'].trim() : null
    if (!slug)    return { ok: false, error: 'slug is required' }
    if (!content) return { ok: false, error: 'content must not be empty' }
    if (!/^[a-z0-9-]+$/.test(slug)) return { ok: false, error: 'slug must be lowercase alphanumeric and hyphens only' }

    const entry = await writeEpisodic(ctx.layout, ctx.sessionId, slug, content)
    ctx.logger.info('mil:memory_write', { slug, path: entry.path })
    return { ok: true, output: `Written: ${entry.path}` }
  },
}
