// fcp_file_read — read a file from disk.
import * as fs from 'node:fs/promises'
import * as path from 'node:path'
import type { ToolHandler, ToolResult, ExecContext } from '../../types/exec.js'

const MAX_BYTES = 512 * 1024  // 512 KB

function extractPath(params: unknown): string | null {
  if (typeof params === 'object' && params !== null && 'path' in params) {
    const p = (params as Record<string, unknown>)['path']
    return typeof p === 'string' ? p.trim() : null
  }
  return null
}

export const fileReadHandler: ToolHandler = {
  name: 'fcp_file_read',
  async execute(params: unknown, ctx: ExecContext): Promise<ToolResult> {
    const filePath = extractPath(params)
    if (!filePath) return { ok: false, error: 'path is required' }
    if (filePath.includes('..')) return { ok: false, error: 'path traversal not allowed' }

    const abs = path.isAbsolute(filePath) ? filePath : path.join(ctx.layout.root, filePath)

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
