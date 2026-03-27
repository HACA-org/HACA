// fcp_shell_run — run a whitelisted shell command within workspace_focus.
// Git is permitted because entity root and workspace are always separate directories.
import * as path from 'node:path'
import { execFile } from 'node:child_process'
import { promisify } from 'node:util'
import { resolveWorkspace, checkInsideWorkspace } from '../workspace.js'
import type { ToolHandler, ToolResult, ExecContext } from '../../types/exec.js'

const execFileAsync = promisify(execFile)

const TIMEOUT_MS   = 10_000
const MAX_OUT_BYTES = 256 * 1024  // 256 KB

// Read-only/info utilities plus git. No destructive ops, no network.
const SAFE_COMMANDS = new Set([
  'ls', 'cat', 'head', 'tail', 'wc', 'grep', 'find',
  'echo', 'pwd', 'date', 'env', 'printenv', 'uname',
  'which', 'stat', 'file', 'diff', 'sort', 'uniq', 'tr',
  'cut', 'awk', 'sed', 'jq',
  'git',
])

interface ShellParams {
  cmd:  string
  args: string[]
  cwd?: string
}

function extractParams(params: unknown): ShellParams | null {
  if (typeof params !== 'object' || params === null) return null
  const p = params as Record<string, unknown>
  const cmd  = typeof p['cmd']  === 'string' ? p['cmd'].trim()  : null
  if (!cmd) return null
  const args = Array.isArray(p['args'])
    ? p['args'].filter((a): a is string => typeof a === 'string')
    : []
  const cwd = typeof p['cwd'] === 'string' ? p['cwd'].trim() : undefined
  return { cmd, args, cwd }
}

export const shellRunHandler: ToolHandler = {
  name: 'fcp_shell_run',
  async execute(params: unknown, ctx: ExecContext): Promise<ToolResult> {
    const parsed = extractParams(params)
    if (!parsed) return { ok: false, error: 'cmd is required' }
    if (!SAFE_COMMANDS.has(parsed.cmd)) {
      return { ok: false, error: `command not in allowlist: ${parsed.cmd}` }
    }

    const workspace = await resolveWorkspace(ctx)
    if (!workspace) return { ok: false, error: 'workspace_focus is not set' }

    // Resolve working directory — default to workspace_focus
    let cwd = workspace
    if (parsed.cwd) {
      const abs = path.isAbsolute(parsed.cwd) ? parsed.cwd : path.join(workspace, parsed.cwd)
      const cwdErr = checkInsideWorkspace(abs, workspace)
      if (cwdErr) return { ok: false, error: cwdErr }
      cwd = abs
    }

    try {
      const { stdout, stderr } = await execFileAsync(parsed.cmd, parsed.args, {
        cwd,
        timeout:   TIMEOUT_MS,
        maxBuffer: MAX_OUT_BYTES,
        env:       { PATH: process.env['PATH'] ?? '/usr/local/bin:/usr/bin:/bin' },
      })
      ctx.logger.info('exec:shell_run', { cmd: parsed.cmd, args: parsed.args })
      const out = stdout + (stderr ? `\nSTDERR:\n${stderr}` : '')
      return { ok: true, output: out.trim() }
    } catch (e: unknown) {
      return { ok: false, error: String(e) }
    }
  },
}
