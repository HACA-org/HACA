// fcp_file_write — write content to a file on disk within workspace_focus.
import * as path from 'node:path'
import { ensureDir, atomicWrite, readJson, fileExists } from '../../store/io.js'
import type { ToolHandler, ToolResult, ExecContext } from '../../types/exec.js'

function extractParams(params: unknown): { path: string; content: string } | null {
  if (typeof params !== 'object' || params === null) return null
  const p = params as Record<string, unknown>
  const filePath = typeof p['path'] === 'string' ? p['path'].trim() : null
  const content  = typeof p['content'] === 'string' ? p['content'] : null
  if (!filePath || content === null) return null
  return { path: filePath, content }
}

async function resolveWorkspace(ctx: ExecContext): Promise<string | null> {
  if (!await fileExists(ctx.layout.state.workspaceFocus)) return null
  try {
    const raw = await readJson(ctx.layout.state.workspaceFocus) as Record<string, unknown>
    return typeof raw['path'] === 'string' ? raw['path'].trim() : null
  } catch {
    return null
  }
}

export const fileWriteHandler: ToolHandler = {
  name: 'fcp_file_write',
  async execute(params: unknown, ctx: ExecContext): Promise<ToolResult> {
    const args = extractParams(params)
    if (!args) return { ok: false, error: 'path and content are required' }

    const workspace = await resolveWorkspace(ctx)
    if (!workspace) return { ok: false, error: 'workspace_focus is not set' }

    const abs = path.isAbsolute(args.path) ? args.path : path.join(workspace, args.path)
    if (!abs.startsWith(workspace + path.sep) && abs !== workspace) {
      return { ok: false, error: 'path is outside workspace_focus' }
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
