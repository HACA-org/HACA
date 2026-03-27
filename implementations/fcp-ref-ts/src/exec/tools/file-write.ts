// fcp_file_write — write content to a file on disk within workspace_focus.
import * as path from 'node:path'
import { ensureDir, atomicWrite } from '../../store/io.js'
import { resolveWorkspace, checkInsideWorkspace } from '../workspace.js'
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
  async execute(params: unknown, ctx: ExecContext): Promise<ToolResult> {
    const args = extractParams(params)
    if (!args) return { ok: false, error: 'path and content are required' }

    const workspace = await resolveWorkspace(ctx)
    if (!workspace) return { ok: false, error: 'workspace_focus is not set' }

    const abs = path.isAbsolute(args.path) ? args.path : path.join(workspace, args.path)
    const err = checkInsideWorkspace(abs, workspace)
    if (err) return { ok: false, error: err }

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
