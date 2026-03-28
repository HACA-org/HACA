// fcp_file_write — write content to a file on disk within workspace_focus.
// Gate: asks on first write of session (inside workspace) + always if outside workspace.
import * as path from 'node:path'
import { ensureDir, atomicWrite } from '../../store/io.js'
import { resolveWorkspace, checkInsideWorkspace } from '../workspace.js'
import { resolveToolApproval } from '../../session/approval.js'
import type { ToolHandler, ToolResult, ExecContext } from '../../types/exec.js'

function extractParams(params: unknown): { path: string; content: string } | null {
  if (typeof params !== 'object' || params === null) return null
  const p = params as Record<string, unknown>
  const filePath = typeof p['path'] === 'string' ? p['path'].trim() : null
  const content  = typeof p['content'] === 'string' ? p['content'] : null
  if (!filePath || content === null) return null
  return { path: filePath, content }
}

export const fileWriteHandler: ToolHandler = {
  name: 'fcp_file_write',
  description: 'Write content to a file within workspace_focus. Asks for approval on the first write of the session (inside workspace) and always if the path is outside the workspace.',
  inputSchema: {
    type: 'object',
    properties: {
      path:    { type: 'string', description: 'File path (relative to workspace_focus, or absolute).' },
      content: { type: 'string', description: 'Content to write.' },
    },
    required: ['path', 'content'],
  },
  async execute(params: unknown, ctx: ExecContext): Promise<ToolResult> {
    const args = extractParams(params)
    if (!args) return { ok: false, error: 'path and content are required' }

    const workspace = await resolveWorkspace(ctx)
    if (!workspace) return { ok: false, error: 'workspace_focus is not set' }

    const abs = path.isAbsolute(args.path) ? args.path : path.join(workspace, args.path)
    const outsideWorkspace = checkInsideWorkspace(abs, workspace) !== null

    if (outsideWorkspace) {
      // Outside workspace — always ask
      const decision = await resolveToolApproval(
        `Write file outside workspace: ${abs}`,
        'once-session-deny',
        ctx.io,
      )
      if (!decision.granted) return { ok: false, error: 'Denied by operator.' }
    } else if (!ctx.firstWriteDone.value) {
      // First write of session inside workspace — ask once
      const decision = await resolveToolApproval(
        `First file write this session: ${abs}`,
        'once-session-deny',
        ctx.io,
      )
      if (!decision.granted) return { ok: false, error: 'Denied by operator.' }
      // 'session' → mark done so subsequent writes are silent
      // 'one-time' → don't mark done, next write will ask again
      if (decision.tier === 'session') ctx.firstWriteDone.value = true
    }

    try {
      await ensureDir(path.dirname(abs))
      await atomicWrite(abs, args.content)
      ctx.logger.info('exec:file_write', { path: abs, bytes: args.content.length })
      return { ok: true, output: `Written: ${abs}` }
    } catch (e: unknown) {
      return { ok: false, error: String(e) }
    }
  },
}
