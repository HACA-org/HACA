// fcp_shell_run — run a whitelisted shell command inside the entity root.
// Only stateless, non-destructive, non-git commands are permitted (§ feedback: shell_run allowlist).
import { execFile } from 'node:child_process'
import { promisify } from 'node:util'
import type { ToolHandler, ToolResult, ExecContext } from '../../types/exec.js'

const execFileAsync = promisify(execFile)

const TIMEOUT_MS   = 10_000
const MAX_OUT_BYTES = 256 * 1024  // 256 KB

// Only basic read-only/info commands. No git, no destructive ops, no network.
const SAFE_COMMANDS = new Set([
  'ls', 'cat', 'head', 'tail', 'wc', 'grep', 'find',
  'echo', 'pwd', 'date', 'env', 'printenv', 'uname',
  'which', 'stat', 'file', 'diff', 'sort', 'uniq', 'tr',
  'cut', 'awk', 'sed', 'jq',
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

    // Resolve working directory — default to entity root
    let cwd = ctx.layout.root
    if (parsed.cwd) {
      if (parsed.cwd.includes('..')) return { ok: false, error: 'path traversal not allowed' }
      cwd = parsed.cwd.startsWith('/') ? parsed.cwd : `${ctx.layout.root}/${parsed.cwd}`
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
