import { exec } from 'node:child_process'
import { promisify } from 'node:util'
import { resolve } from 'node:path'
import { homedir } from 'node:os'
import type { Layout } from '../../store/layout.js'
import type { Logger } from '../../logger/logger.js'
import type { ToolHandler } from '../../session/loop.js'
import { readAllowlist, isCommandAllowed, addToAllowlist } from '../allowlist.js'
import type { ExecContext } from '../types.js'

const execAsync = promisify(exec)

const SAFE_COMMANDS = ['grep', 'ls', 'mkdir', 'cat', 'echo', 'pwd', 'find', 'wc', 'head', 'tail', 'sort', 'uniq', 'diff']
const TIMEOUT_MS = 30_000

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

export function createShellRunTool(
  layout: Layout,
  logger: Logger,
  ctx: ExecContext,
  requestApproval: (prompt: string) => Promise<'once' | 'session' | 'allow' | 'deny'>,
): ToolHandler {
  return {
    definition: {
      name: 'shellRun',
      description: 'Execute a shell command. Restricted to pre-approved commands or operator-approved execution.',
      input_schema: {
        type: 'object',
        properties: {
          command: { type: 'string', description: 'The shell command to execute' },
          cwd: { type: 'string', description: 'Working directory (must be inside workspace)' },
        },
        required: ['command'],
      },
    },
    async handle(input) {
      const command = String(input['command'] ?? '').trim()
      if (!command) return 'Error: command is required'

      const cwd = input['cwd'] ? String(input['cwd']) : (ctx.workspaceFocus ?? process.cwd())

      // Block access to ~/.fcp internals
      if (isInsideFcpDir(cwd)) {
        return 'Error: shellRun cannot operate inside ~/.fcp'
      }

      // Validate cwd is inside workspace if focus is set
      if (ctx.workspaceFocus && !isInsideWorkspace(cwd, ctx.workspaceFocus)) {
        return `Error: cwd is outside workspace focus (${ctx.workspaceFocus})`
      }

      const allowlist = await readAllowlist(layout)
      const cmdBase = command.trim().split(/\s+/)[0] ?? ''
      const isPreApproved = isCommandAllowed(allowlist, command)

      if (!isPreApproved) {
        const decision = await requestApproval(`shellRun: ${command}`)
        if (decision === 'deny') return 'Execution denied by operator.'
        if (decision === 'allow') {
          // Only persist if it's a known safe command
          if (SAFE_COMMANDS.includes(cmdBase)) {
            await addToAllowlist(layout, 'shellRun', cmdBase)
          }
        }
        // 'once' and 'session' handled by loop-level sessionGrants — proceed
      }

      try {
        await logger.info('exec', 'shell_run', { command, cwd })
        const { stdout, stderr } = await execAsync(command, { cwd, timeout: TIMEOUT_MS })
        const out = stdout.trim()
        const err = stderr.trim()
        return [out, err ? `stderr: ${err}` : ''].filter(Boolean).join('\n') || '(no output)'
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e)
        await logger.error('exec', 'shell_run_error', { command, error: msg })
        return `Error: ${msg}`
      }
    },
  }
}
