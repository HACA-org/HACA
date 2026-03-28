// fcp_session_close — SIL tool: signal normal session close.
// The loop detects this result and exits cleanly.
import type { ToolHandler, ToolResult, ExecContext } from '../../types/exec.js'

export const SESSION_CLOSE_SIGNAL = '__fcp_session_close__'

export const sessionCloseHandler: ToolHandler = {
  name: 'fcp_session_close',
  description: 'Signal a normal session close. Must be called after fcp_closure_payload. The loop exits cleanly and the Sleep Cycle begins.',
  inputSchema: { type: 'object', properties: {} },
  async execute(_params: unknown, ctx: ExecContext): Promise<ToolResult> {
    ctx.logger.info('sil:session_close')
    return { ok: true, output: SESSION_CLOSE_SIGNAL }
  },
}
