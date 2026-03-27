// fcp_session_close — SIL tool: signal normal session close.
// The loop detects this result and exits cleanly.
import type { ToolHandler, ToolResult, ExecContext } from '../../types/exec.js'

export const SESSION_CLOSE_SIGNAL = '__fcp_session_close__'

export const sessionCloseHandler: ToolHandler = {
  name: 'fcp_session_close',
  async execute(_params: unknown, ctx: ExecContext): Promise<ToolResult> {
    ctx.logger.info('sil:session_close')
    return { ok: true, output: SESSION_CLOSE_SIGNAL }
  },
}
