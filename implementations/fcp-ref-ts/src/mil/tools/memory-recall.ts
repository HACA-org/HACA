// fcp_memory_recall — MIL tool: query the memory store and return matching content.
import * as fs from 'node:fs/promises'
import * as path from 'node:path'
import { searchSemantic } from '../semantic.js'
import { searchEpisodic } from '../episodic.js'
import type { ToolHandler, ToolResult, ExecContext } from '../../types/exec.js'

export const memoryRecallHandler: ToolHandler = {
  name: 'fcp_memory_recall',
  description: 'Query the memory store (semantic + episodic) and return matching content. Use this to recall past context, facts, or episodic events.',
  inputSchema: {
    type: 'object',
    properties: {
      query: { type: 'string', description: 'Search query string.' },
    },
    required: ['query'],
  },
  async execute(params: unknown, ctx: ExecContext): Promise<ToolResult> {
    if (typeof params !== 'object' || params === null || typeof (params as Record<string, unknown>)['query'] !== 'string') {
      return { ok: false, error: 'query is required' }
    }
    const query = ((params as Record<string, unknown>)['query'] as string).trim()
    if (!query) return { ok: false, error: 'query must not be empty' }

    const [semanticHits, episodicPaths] = await Promise.all([
      searchSemantic(ctx.layout, query),
      searchEpisodic(ctx.layout, query),
    ])

    const sections: string[] = []

    for (const hit of semanticHits) {
      const abs = path.join(ctx.layout.root, hit.path)
      try {
        const content = await fs.readFile(abs, 'utf8')
        if (content) sections.push(`[semantic:${hit.slug}]\n${content}`)
      } catch (e: unknown) {
        const code = (e as NodeJS.ErrnoException).code
        if (code !== 'ENOENT') ctx.logger.warn('mil:memory_recall:read_error', { path: hit.path, error: String(e) })
      }
    }

    for (const p of episodicPaths) {
      const abs = path.join(ctx.layout.root, p)
      try {
        const content = await fs.readFile(abs, 'utf8')
        if (content) sections.push(`[episodic:${path.basename(p, '.md')}]\n${content}`)
      } catch (e: unknown) {
        const code = (e as NodeJS.ErrnoException).code
        if (code !== 'ENOENT') ctx.logger.warn('mil:memory_recall:read_error', { path: p, error: String(e) })
      }
    }

    if (sections.length === 0) return { ok: true, output: `No memory found for query: "${query}"` }

    ctx.logger.info('mil:memory_recall', { query, hits: sections.length })
    return { ok: true, output: sections.join('\n\n---\n\n') }
  },
}
