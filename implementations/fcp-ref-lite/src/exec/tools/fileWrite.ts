import { resolve, dirname } from 'node:path'
import { homedir } from 'node:os'
import { mkdir } from 'node:fs/promises'
import type { Logger } from '../../logger/logger.js'
import type { ToolHandler } from '../../session/loop.js'
import { writeJson } from '../../store/io.js'
import type { ExecContext } from '../types.js'
import { writeFile } from 'node:fs/promises'

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

export function createFileWriteTool(logger: Logger, ctx: ExecContext): ToolHandler {
  return {
    definition: {
      name: 'fileWrite',
      description: 'Write content to a file inside the workspace. Path must be inside the current workspace focus.',
      input_schema: {
        type: 'object',
        properties: {
          path: { type: 'string', description: 'Path to the file (relative to workspace or absolute)' },
          content: { type: 'string', description: 'Content to write' },
        },
        required: ['path', 'content'],
      },
    },
    async handle(input) {
      if (!ctx.workspaceFocus) return 'Error: no workspace focus set. Use /focus <path> to set one.'

      const raw = String(input['path'] ?? '').trim()
      const content = String(input['content'] ?? '')
      if (!raw) return 'Error: path is required'

      const abs = resolve(ctx.workspaceFocus, raw)

      if (isInsideFcpDir(abs)) return 'Error: cannot write files inside ~/.fcp'
      if (!isInsideWorkspace(abs, ctx.workspaceFocus)) {
        return `Error: path is outside workspace focus (${ctx.workspaceFocus})`
      }

      try {
        await mkdir(dirname(abs), { recursive: true })
        await writeFile(abs, content, 'utf8')
        await logger.info('exec', 'file_write', { path: abs, bytes: content.length })
        return `Written: ${abs} (${content.length} bytes)`
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e)
        return `Error: ${msg}`
      }
    },
  }
}
