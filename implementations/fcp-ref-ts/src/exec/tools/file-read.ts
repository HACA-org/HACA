// fcp_file_read — read a file from disk within workspace_focus.
import * as fs from 'node:fs/promises'
import * as path from 'node:path'
import { readJson, fileExists } from '../../store/io.js'
import type { ToolHandler, ToolResult, ExecContext } from '../../types/exec.js'

const MAX_BYTES = 512 * 1024  // 512 KB

function extractPath(params: unknown): string | null {
  if (typeof params === 'object' && params !== null && 'path' in params) {
    const p = (params as Record<string, unknown>)['path']
    return typeof p === 'string' ? p.trim() : null
  }
  return null
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

export const fileReadHandler: ToolHandler = {
  name: 'fcp_file_read',
  async execute(params: unknown, ctx: ExecContext): Promise<ToolResult> {
    const filePath = extractPath(params)
    if (!filePath) return { ok: false, error: 'path is required' }

    const workspace = await resolveWorkspace(ctx)
    if (!workspace) return { ok: false, error: 'workspace_focus is not set' }

    const abs = path.isAbsolute(filePath) ? filePath : path.join(workspace, filePath)
    if (!abs.startsWith(workspace + path.sep) && abs !== workspace) {
      return { ok: false, error: 'path is outside workspace_focus' }
    }

    try {
      const buf = await fs.readFile(abs)
      if (buf.byteLength > MAX_BYTES) {
        return { ok: false, error: `file too large (${buf.byteLength} bytes, max ${MAX_BYTES})` }
      }
      ctx.logger.info('exec:file_read', { path: abs })
      return { ok: true, output: buf.toString('utf8') }
    } catch (e: unknown) {
      return { ok: false, error: String(e) }
    }
  },
}
