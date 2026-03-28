// fcp_closure_payload — MIL tool: stage the session closure payload atomically.
// FCP writes it to state/pending-closure.json before the Sleep Cycle begins.
import { ensureDir, writeJson } from '../../store/io.js'
import { ClosurePayloadSchema } from '../../types/formats/memory.js'
import type { ToolHandler, ToolResult, ExecContext } from '../../types/exec.js'

export const closurePayloadHandler: ToolHandler = {
  name: 'fcp_closure_payload',
  description: 'Stage the session closure payload before calling fcp_session_close. Required for normal session close — the payload is consumed by the Sleep Cycle for memory consolidation.',
  inputSchema: {
    type: 'object',
    properties: {
      type:          { type: 'string', enum: ['closure_payload'] },
      consolidation: { type: 'string', description: 'Summary of what was accomplished this session.' },
      promotion:     { type: 'array', items: { type: 'string' }, description: 'Memory slugs to promote to semantic memory.' },
      workingMemory: {
        type: 'array',
        description: 'Pointers to episodic/semantic memory entries the next session needs to resume context. path is the relative path to the memory file (e.g. memory/episodic/.../slug.md or memory/semantic/slug.md).',
        items: {
          type: 'object',
          properties: {
            priority: { type: 'integer', minimum: 1, description: 'Importance rank (higher = more important, loaded first).' },
            path:     { type: 'string',  description: 'Relative path to the memory entry (episodic or semantic slug).' },
          },
          required: ['priority', 'path'],
        },
      },
      sessionHandoff: {
        type: 'object',
        description: 'Narrative context that explains the working memory entries and what the next session should do to resume.',
        properties: {
          pendingTasks: { type: 'array', items: { type: 'string' } },
          nextSteps:    { type: 'string' },
        },
        required: ['pendingTasks', 'nextSteps'],
      },
    },
    required: ['type', 'consolidation', 'promotion', 'workingMemory', 'sessionHandoff'],
  },
  async execute(params: unknown, ctx: ExecContext): Promise<ToolResult> {
    const parsed = ClosurePayloadSchema.safeParse(params)
    if (!parsed.success) {
      return { ok: false, error: `invalid closure payload: ${parsed.error.message}` }
    }
    await ensureDir(ctx.layout.state.dir)
    await writeJson(ctx.layout.state.pendingClosure, parsed.data)
    ctx.logger.info('mil:closure_payload', { promotion: parsed.data.promotion.length })
    return { ok: true, output: 'Closure payload staged.' }
  },
}
