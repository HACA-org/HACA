import { resolve } from 'node:path'
import { homedir } from 'node:os'
import { readFile } from 'node:fs/promises'
import { existsSync } from 'node:fs'
import type { Logger } from '../../logger/logger.js'
import type { ToolHandler } from '../../session/loop.js'
import type { ExecContext } from '../types.js'

const MAX_BYTES = 512 * 1024 // 512KB

function isInsideWorkspace(path: string, workspaceFocus: string): boolean {
  const abs = resolve(path)
  const ws = resolve(workspaceFocus)
  return abs === ws || abs.startsWith(ws + '/')
}

function isInsideFcpDir(path: string): boolean {
  const fcpDir = resolve(homedir(), '.fcp')
  const abs = resolve(path)
  return abs === fcpDir || abs.startsWith(fcpDir + '/')
}

export function createFileReadTool(logger: Logger, ctx: ExecContext): ToolHandler {
  return {
    definition: {
      name: 'fileRead',
      description: 'Read a file from the workspace. Path must be inside the current workspace focus.',
      input_schema: {
        type: 'object',
        properties: {
          path: { type: 'string', description: 'Path to the file (relative to workspace or absolute)' },
        },
        required: ['path'],
      },
    },
    async handle(input) {
      if (!ctx.workspaceFocus) return 'Error: no workspace focus set. Use /focus <path> to set one.'

      const raw = String(input['path'] ?? '').trim()
      if (!raw) return 'Error: path is required'

      const abs = resolve(ctx.workspaceFocus, raw)

      if (isInsideFcpDir(abs)) return 'Error: cannot read files inside ~/.fcp'
      if (!isInsideWorkspace(abs, ctx.workspaceFocus)) {
        return `Error: path is outside workspace focus (${ctx.workspaceFocus})`
      }

      if (!existsSync(abs)) return `Error: file not found: ${abs}`

      try {
        const buf = await readFile(abs)
        if (buf.byteLength > MAX_BYTES) {
          return `Error: file too large (${buf.byteLength} bytes, max ${MAX_BYTES})`
        }
        await logger.info('exec', 'file_read', { path: abs })
        return buf.toString('utf8')
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e)
        return `Error: ${msg}`
      }
    },
  }
}
