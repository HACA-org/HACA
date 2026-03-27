// fcp_shell_run — run a shell command within workspace_focus.
// Allowed commands come from state/allowlist.json (no hardcoded list).
// Gate: asks if command not in allowlist (once/session/add-to-allowlist/deny).
// Gate: asks if cwd is outside workspace (once/session/deny).
import * as path from 'node:path'
import { execFile } from 'node:child_process'
import { promisify } from 'node:util'
import { resolveWorkspace, checkInsideWorkspace } from '../workspace.js'
import { resolveToolApproval } from '../../session/approval.js'
import type { ToolHandler, ToolResult, ExecContext } from '../../types/exec.js'

const execFileAsync = promisify(execFile)

const TIMEOUT_MS    = 10_000
const MAX_OUT_BYTES = 256 * 1024  // 256 KB

interface ShellParams {
  cmd:  string
  args: string[]
  cwd:  string | undefined
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

    const workspace = await resolveWorkspace(ctx)
    if (!workspace) return { ok: false, error: 'workspace_focus is not set' }

    // Resolve working directory
    let cwd = workspace
    if (parsed.cwd) {
      const abs = path.isAbsolute(parsed.cwd) ? parsed.cwd : path.join(workspace, parsed.cwd)
      const cwdErr = checkInsideWorkspace(abs, workspace)
      if (cwdErr) {
        // cwd outside workspace — ask operator
        const decision = await resolveToolApproval(
          `Run command with cwd outside workspace: ${abs}`,
          'once-session-deny',
          ctx.io,
        )
        if (!decision.granted) return { ok: false, error: 'Denied by operator.' }
      }
      cwd = abs
    }

    // Gate: command not in allowlist
    if (!ctx.policy.commands.includes(parsed.cmd)) {
      const decision = await resolveToolApproval(
        `Run command not in allowlist: ${parsed.cmd}`,
        'once-session-allowlist-deny',
        ctx.io,
      )
      if (!decision.granted) return { ok: false, error: 'Denied by operator.' }
      if (decision.tier === 'session')    await ctx.policy.addCommand(parsed.cmd, 'session')
      if (decision.tier === 'persistent') await ctx.policy.addCommand(parsed.cmd, 'persistent')
      // tier === 'one-time': run once without adding to policy
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
