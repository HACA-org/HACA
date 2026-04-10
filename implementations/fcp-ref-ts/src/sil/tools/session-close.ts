// fcp_session_close — SIL tool: signal normal session close or reboot.
// The loop detects the signal and exits; run.ts decides whether to reboot.
import type { ToolHandler, ToolResult, ExecContext } from '../../types/exec.js'

export const SESSION_CLOSE_SIGNAL  = '__fcp_session_close__'
export const SESSION_REBOOT_SIGNAL = '__fcp_session_reboot__'

export const sessionCloseHandler: ToolHandler = {
  name: 'fcp_session_close',
  description: 'Signal session close. Call after fcp_closure_payload. The FCP Sleep Cycle begins. Pass reboot: true when a new clean session is required immediately after.',
  inputSchema: {
    type: 'object',
    properties: {
      reboot: {
        type: 'boolean',
        description: 'If true, FCP will start a new session after the Sleep Cycle.',
      },
    },
  },
  async execute(params: unknown, ctx: ExecContext): Promise<ToolResult> {
    const reboot = (params as Record<string, unknown>)?.['reboot'] === true
    ctx.logger.info('sil:session_close', { reboot })
    return { ok: true, output: reboot ? SESSION_REBOOT_SIGNAL : SESSION_CLOSE_SIGNAL }
  },
}
