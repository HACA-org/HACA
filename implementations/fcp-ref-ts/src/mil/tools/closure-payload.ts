// fcp_closure_payload — MIL tool: stage the session closure payload atomically.
// FCP writes it to state/pending-closure.json before the Sleep Cycle begins.
import { ensureDir, writeJson } from '../../store/io.js'
import { ClosurePayloadSchema } from '../../types/formats/memory.js'
import type { ToolHandler, ToolResult, ExecContext } from '../../types/exec.js'

export const closurePayloadHandler: ToolHandler = {
  name: 'fcp_closure_payload',
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
