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
        description: 'Working memory entries (key-value pairs) to carry forward.',
        items: {
          type: 'object',
          properties: {
            key:   { type: 'string' },
            value: { type: 'string' },
          },
          required: ['key', 'value'],
        },
      },
      sessionHandoff: {
        type: 'object',
        description: 'Summary of pending tasks and next steps for the next session.',
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
